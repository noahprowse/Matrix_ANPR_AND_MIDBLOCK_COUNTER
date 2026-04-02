"""Base subprocess worker for video processing.

Runs inside a multiprocessing.Process (NOT a QThread). Subclasses implement
_load_models() and process_frame() to provide module-specific logic (ANPR,
midblock counting, etc.).
"""

from __future__ import annotations

import abc
import logging
import os
import signal
import time
from multiprocessing import Event, Queue
from typing import Any, Optional

import cv2

from src.engine.ipc_protocol import IPCMessage, MsgType

logger = logging.getLogger(__name__)


class BaseVideoWorker(abc.ABC):
    """Base class for a video-processing worker that runs in its own process.

    Parameters:
        stream_id:       Unique integer identifying this processing stream.
        video_paths:     Ordered list of video file paths to process.
        result_queue:    Shared multiprocessing.Queue for sending IPCMessages
                         back to the main/GUI process.
        shutdown_event:  Shared multiprocessing.Event; when set the worker
                         should stop as soon as possible.
        config:          Arbitrary configuration dict (model paths, thresholds,
                         classification settings, etc.).
        use_gpu:         Whether this worker should attempt GPU inference.
        preview_enabled: Whether to send preview frames back over the queue.
        chunks:          Optional list of VideoChunk dicts for frame-range
                         processing.  When provided, each entry specifies
                         {video_path, start_frame, end_frame, overlap_frames,
                         chunk_index, total_chunks}.  ``video_paths`` is
                         ignored when chunks are present.
    """

    # Maximum preview frame rate (frames per second)
    _PREVIEW_MAX_FPS: float = 3.0

    def __init__(
        self,
        stream_id: int,
        video_paths: list[str],
        result_queue: Queue,
        shutdown_event: Event,
        config: dict,
        use_gpu: bool = False,
        preview_enabled: bool = False,
        chunks: list[dict] | None = None,
    ) -> None:
        self.stream_id = stream_id
        self.video_paths = list(video_paths)
        self.result_queue = result_queue
        self.shutdown_event = shutdown_event
        self.config = config
        self.use_gpu = use_gpu
        self.preview_enabled = preview_enabled
        self.chunks: list[dict] = chunks or []

        # Internal bookkeeping
        self._last_preview_time: float = 0.0
        self._preview_interval: float = 1.0 / self._PREVIEW_MAX_FPS

    # ── Public entry point (called inside the subprocess) ─────────────

    def run(self) -> None:
        """Main loop: load models then iterate through every video file."""
        # Ignore SIGINT so the parent process controls shutdown cleanly
        signal.signal(signal.SIGINT, signal.SIG_IGN)

        # Disable OpenCV's internal threading to avoid conflicts with
        # Python multiprocessing (prevents "returned a result with an
        # exception set" errors from cv2.VideoCapture.read()).
        cv2.setNumThreads(0)

        # Build the work list — either chunks or plain video paths
        work_items = self._build_work_items()

        cap: Optional[cv2.VideoCapture] = None
        try:
            self._push_status("Loading models...")
            self._load_models()
            self._push_status("Models loaded")

            total_items = len(work_items)

            for item_idx, item in enumerate(work_items):
                if self.shutdown_event.is_set():
                    break

                video_path = item["path"]
                start_frame = item["start_frame"]
                end_frame = item["end_frame"]
                overlap_frames = item["overlap_frames"]
                chunk_index = item["chunk_index"]
                total_chunks = item["total_chunks"]

                filename = os.path.basename(video_path)
                chunk_label = (
                    f" (chunk {chunk_index + 1}/{total_chunks})"
                    if total_chunks > 1 else ""
                )
                self._push_status(
                    f"Opening {filename}{chunk_label}"
                    f" ({item_idx + 1}/{total_items})"
                )

                cap = cv2.VideoCapture(video_path)
                if not cap.isOpened():
                    self._push_error(f"Failed to open video: {video_path}")
                    continue

                file_total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

                # Determine the frame range for this work item
                effective_end = end_frame if end_frame > 0 else file_total_frames
                chunk_total = effective_end - start_frame

                # Seek to start frame if needed
                if start_frame > 0:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

                video_info = {
                    "path": video_path,
                    "filename": filename,
                    "total_frames": chunk_total,
                    "fps": fps,
                    "width": width,
                    "height": height,
                    "video_index": item_idx,
                    "total_videos": total_items,
                    "start_frame": start_frame,
                    "end_frame": effective_end,
                    "overlap_frames": overlap_frames,
                    "chunk_index": chunk_index,
                    "total_chunks": total_chunks,
                    "is_overlap": False,
                }

                # Notify that a new video/chunk has started
                self._push_msg(MsgType.VIDEO_STARTED, {
                    "filename": filename,
                    "video_index": item_idx,
                    "total_frames": chunk_total,
                    "chunk_index": chunk_index,
                    "total_chunks": total_chunks,
                })

                frames_read = 0
                while not self.shutdown_event.is_set():
                    # Stop at end_frame boundary
                    current_abs_frame = start_frame + frames_read
                    if end_frame > 0 and current_abs_frame >= end_frame:
                        break

                    try:
                        ret, frame = cap.read()
                    except Exception as read_exc:
                        logger.warning(
                            "Worker %d: cap.read() exception at frame %d: %s",
                            self.stream_id, current_abs_frame, read_exc,
                        )
                        break
                    if not ret:
                        break

                    # Tag whether this frame is in the overlap zone
                    video_info["is_overlap"] = (
                        frames_read < overlap_frames and chunk_index > 0
                    )

                    # Pass the absolute frame number to subclass
                    self.process_frame(frame, current_abs_frame, video_info)

                    # Send preview frame (throttled)
                    if self.preview_enabled:
                        self._maybe_push_frame(frame)

                    # Send progress update
                    frames_read += 1
                    if chunk_total > 0:
                        percent = int((frames_read / chunk_total) * 100)
                        overall = int(
                            ((item_idx * chunk_total + frames_read)
                             / (total_items * chunk_total)) * 100
                        )
                        self._push_progress(
                            percent, overall, frames_read, chunk_total,
                        )

                cap.release()
                cap = None
                self.on_video_complete(video_info)

            # All videos/chunks done (or shutdown requested)
            if self.shutdown_event.is_set():
                self._push_status("Stopped by user")
            self._push_finished()

        except Exception as exc:
            logger.exception("Worker %d crashed", self.stream_id)
            self._push_error(str(exc))
        finally:
            if cap is not None:
                cap.release()

    # ── Work-item builder ────────────────────────────────────────────

    def _build_work_items(self) -> list[dict]:
        """Convert chunks or plain video_paths into a uniform work list."""
        if self.chunks:
            return [
                {
                    "path": c["video_path"],
                    "start_frame": c.get("start_frame", 0),
                    "end_frame": c.get("end_frame", 0),
                    "overlap_frames": c.get("overlap_frames", 0),
                    "chunk_index": c.get("chunk_index", 0),
                    "total_chunks": c.get("total_chunks", 1),
                }
                for c in self.chunks
            ]
        # Fallback: whole-file processing (backwards compatible)
        return [
            {
                "path": p,
                "start_frame": 0,
                "end_frame": 0,
                "overlap_frames": 0,
                "chunk_index": 0,
                "total_chunks": 1,
            }
            for p in self.video_paths
        ]

    # ── Abstract methods (subclasses must implement) ──────────────────

    @abc.abstractmethod
    def _load_models(self) -> None:
        """Load ML models (YOLO, PaddleOCR, etc.) for this worker."""

    def on_video_complete(self, video_info: dict) -> None:
        """Hook called after each video completes. Override for cleanup.

        Use this to reset tracker state, finalize per-video results, etc.
        """

    @abc.abstractmethod
    def process_frame(
        self,
        frame: Any,
        frame_num: int,
        video_info: dict,
    ) -> None:
        """Process a single video frame.

        Implementations should call self._push_result() for each detection.

        Args:
            frame:      BGR numpy array from cv2.VideoCapture.
            frame_num:  Zero-based index of this frame within the current video.
            video_info: Dict with keys: path, filename, total_frames, fps,
                        width, height, video_index, total_videos.
        """

    # ── IPC helper methods ────────────────────────────────────────────

    def _push_msg(self, msg_type: MsgType, payload: dict) -> None:
        """Put an IPCMessage on the result queue."""
        msg = IPCMessage(
            stream_id=self.stream_id,
            msg_type=msg_type,
            payload=payload,
            timestamp=time.time(),
        )
        try:
            self.result_queue.put_nowait(msg)
        except Exception:
            # Queue full or broken — drop the message silently
            pass

    def _push_progress(
        self,
        video_percent: int,
        overall_percent: int,
        frame_num: int,
        total_frames: int,
    ) -> None:
        """Send a progress update."""
        self._push_msg(MsgType.PROGRESS, {
            "video_percent": video_percent,
            "overall_percent": overall_percent,
            "frame_num": frame_num,
            "total_frames": total_frames,
        })

    def _push_result(self, result: dict) -> None:
        """Send an individual detection result."""
        self._push_msg(MsgType.RESULT, result)

    def _push_frame(self, jpeg_bytes: bytes) -> None:
        """Send a JPEG-encoded preview frame."""
        self._push_msg(MsgType.FRAME, {"jpeg": jpeg_bytes})

    def _push_status(self, text: str) -> None:
        """Send a status text update."""
        self._push_msg(MsgType.STATUS, {"text": text})

    def _push_finished(self) -> None:
        """Signal that this stream has completed processing."""
        self._push_msg(MsgType.FINISHED, {})

    def _push_error(self, message: str) -> None:
        """Signal an error on this stream."""
        self._push_msg(MsgType.ERROR, {"message": message})

    # ── Preview throttling ────────────────────────────────────────────

    def _maybe_push_frame(self, frame: Any) -> None:
        """Encode and send a preview frame if enough time has elapsed."""
        now = time.time()
        if now - self._last_preview_time < self._preview_interval:
            return
        self._last_preview_time = now

        try:
            # Resize for preview (max 480px wide)
            h, w = frame.shape[:2]
            if w > 480:
                scale = 480 / w
                frame = cv2.resize(
                    frame,
                    (480, int(h * scale)),
                    interpolation=cv2.INTER_AREA,
                )
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
            if ok:
                self._push_frame(buf.tobytes())
        except Exception:
            pass  # Preview is best-effort
