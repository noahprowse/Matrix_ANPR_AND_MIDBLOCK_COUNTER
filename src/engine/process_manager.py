"""Orchestrator for the multiprocessing worker pool.

Spawns one multiprocessing.Process per VideoAssignment, monitors lifecycle,
and provides clean start/stop semantics.

Includes utilities for splitting long videos into frame-range chunks so
multiple workers can process a single file in parallel.
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict
from multiprocessing import Event, Process, Queue
from typing import Optional

import cv2

from src.common.data_models import VideoAssignment, VideoChunk
from src.engine.base_worker import BaseVideoWorker

logger = logging.getLogger(__name__)

# Timeout (seconds) when joining worker processes during shutdown
_JOIN_TIMEOUT = 10.0

# Default overlap between chunks (in seconds) to allow ByteTrack to
# re-acquire vehicles that straddle a chunk boundary.
DEFAULT_OVERLAP_SECONDS = 30

# Minimum chunk duration (seconds). Don't split if a chunk would be
# shorter than this.
MIN_CHUNK_SECONDS = 60


def _worker_entry(
    worker_class: type,
    stream_id: int,
    video_paths: list[str],
    result_queue: Queue,
    shutdown_event: Event,
    config: dict,
    use_gpu: bool,
    preview_enabled: bool,
    chunks: list[dict] | None = None,
) -> None:
    """Top-level function executed inside each spawned process.

    Instantiates the worker class and calls its run() method.
    Must be a module-level function so it is picklable.
    """
    worker = worker_class(
        stream_id=stream_id,
        video_paths=video_paths,
        result_queue=result_queue,
        shutdown_event=shutdown_event,
        config=config,
        use_gpu=use_gpu,
        preview_enabled=preview_enabled,
        chunks=chunks,
    )
    worker.run()


# ── Video distribution helpers ───────────────────────────────────────


def distribute_videos(
    all_paths: list[str],
    num_streams: int,
) -> list[list[str]]:
    """Distribute video paths across *num_streams* buckets using round-robin.

    Returns a list of lists — one per stream — each containing the video
    paths assigned to that stream.

    Example::

        >>> distribute_videos(["a", "b", "c", "d", "e"], 3)
        [['a', 'd'], ['b', 'e'], ['c']]
    """
    if num_streams <= 0:
        return []
    buckets: list[list[str]] = [[] for _ in range(num_streams)]
    for idx, path in enumerate(all_paths):
        buckets[idx % num_streams].append(path)
    return buckets


def _get_video_info(video_path: str) -> tuple[int, float]:
    """Return (total_frames, fps) for a video file."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return 0, 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.release()
    return total, fps


def chunk_video(
    video_path: str,
    num_chunks: int,
    overlap_seconds: float = DEFAULT_OVERLAP_SECONDS,
) -> list[VideoChunk]:
    """Split a single video file into *num_chunks* frame-range chunks.

    Each chunk (except the first) includes ``overlap_seconds`` worth of
    extra frames at the start that overlap with the previous chunk.  The
    overlap zone allows ByteTrack to re-acquire vehicles so they aren't
    double-counted.  The main process uses the ``is_overlap`` flag on
    each result to deduplicate.

    Returns a list of VideoChunk dataclasses.
    """
    total_frames, fps = _get_video_info(video_path)
    if total_frames <= 0 or num_chunks <= 1:
        return [VideoChunk(
            video_path=video_path,
            start_frame=0,
            end_frame=0,  # 0 = "to end"
            overlap_frames=0,
            chunk_index=0,
            total_chunks=1,
        )]

    overlap_frames = int(overlap_seconds * fps)
    min_chunk_frames = int(MIN_CHUNK_SECONDS * fps)

    # Calculate base chunk size (without overlap)
    base_chunk_size = total_frames // num_chunks
    if base_chunk_size < min_chunk_frames:
        # Video too short to split into this many chunks — reduce
        num_chunks = max(1, total_frames // min_chunk_frames)
        if num_chunks <= 1:
            return [VideoChunk(
                video_path=video_path,
                start_frame=0,
                end_frame=0,
                overlap_frames=0,
                chunk_index=0,
                total_chunks=1,
            )]
        base_chunk_size = total_frames // num_chunks

    chunks: list[VideoChunk] = []
    for i in range(num_chunks):
        # Content start (where this chunk's "unique" frames begin)
        content_start = i * base_chunk_size

        # Actual start (include overlap from previous chunk)
        if i == 0:
            actual_start = 0
            chunk_overlap = 0
        else:
            actual_start = max(0, content_start - overlap_frames)
            chunk_overlap = content_start - actual_start

        # End frame
        if i == num_chunks - 1:
            end_frame = 0  # to end of file
        else:
            end_frame = (i + 1) * base_chunk_size

        chunks.append(VideoChunk(
            video_path=video_path,
            start_frame=actual_start,
            end_frame=end_frame,
            overlap_frames=chunk_overlap,
            chunk_index=i,
            total_chunks=num_chunks,
        ))

    return chunks


def create_chunked_assignments(
    video_paths: list[str],
    max_workers: int,
    chunk_duration_minutes: float = 15.0,
    overlap_seconds: float = DEFAULT_OVERLAP_SECONDS,
    use_gpu: bool = False,
) -> list[VideoAssignment]:
    """Build VideoAssignment list with automatic video chunking.

    For each video:
      - If the video is shorter than ``chunk_duration_minutes``, assign
        it as a single whole-file work item.
      - If longer, split it into chunks of ~``chunk_duration_minutes``
        and assign each chunk to a separate worker.

    Total workers are capped at ``max_workers``.

    Returns one VideoAssignment per worker.
    """
    # First pass: build all chunks across all videos
    all_chunks: list[VideoChunk] = []
    for video_path in video_paths:
        total_frames, fps = _get_video_info(video_path)
        if total_frames <= 0:
            logger.warning("Skipping unreadable video: %s", video_path)
            continue

        duration_sec = total_frames / fps
        desired_chunks = max(1, int(duration_sec / (chunk_duration_minutes * 60)))
        # Cap per-video chunks so we don't exceed max_workers on one file
        desired_chunks = min(desired_chunks, max_workers)

        chunks = chunk_video(video_path, desired_chunks, overlap_seconds)
        all_chunks.extend(chunks)

    if not all_chunks:
        return []

    # Cap total assignments at max_workers by distributing chunks
    # round-robin across workers
    actual_workers = min(max_workers, len(all_chunks))
    assignments: list[VideoAssignment] = []
    for i in range(actual_workers):
        assignments.append(VideoAssignment(
            stream_id=i,
            video_paths=[],
            use_gpu=use_gpu,
            preview_enabled=False,
            chunks=[],
        ))

    for idx, chunk in enumerate(all_chunks):
        worker_idx = idx % actual_workers
        assignments[worker_idx].chunks.append(chunk)

    # Remove any empty assignments
    assignments = [a for a in assignments if a.chunks]

    logger.info(
        "Created %d workers for %d video(s) (%d total chunks)",
        len(assignments), len(video_paths), len(all_chunks),
    )
    return assignments


class ProcessManager:
    """Manages spawning and lifecycle of video-processing worker processes.

    Typical usage::

        mgr = ProcessManager()
        mgr.configure(assignments, MyWorkerClass)
        mgr.start()          # spawns processes
        ...                   # MonitorBridge reads from shared queue
        mgr.stop()            # graceful shutdown
    """

    def __init__(self) -> None:
        self._assignments: list[VideoAssignment] = []
        self._worker_class: Optional[type] = None
        self._processes: list[Process] = []
        self._result_queue: Optional[Queue] = None
        self._shutdown_event: Optional[Event] = None
        self._config: dict = {}
        self._running = False

    # ── Configuration ─────────────────────────────────────────────────

    def configure(
        self,
        video_assignments: list[VideoAssignment],
        worker_class: type,
        config: dict | None = None,
    ) -> None:
        """Store assignments and the worker class to use.

        Args:
            video_assignments: One VideoAssignment per stream.
            worker_class:      A BaseVideoWorker subclass.
            config:            Shared configuration dict passed to every worker.
        """
        if self._running:
            raise RuntimeError("Cannot reconfigure while processing is running")
        self._assignments = list(video_assignments)
        self._worker_class = worker_class
        self._config = config or {}

    # ── Lifecycle ─────────────────────────────────────────────────────

    @property
    def result_queue(self) -> Optional[Queue]:
        """The shared multiprocessing.Queue used by all workers."""
        return self._result_queue

    def start(self) -> Queue:
        """Spawn a process for each assignment and return the shared queue.

        Returns:
            The multiprocessing.Queue that all workers will push
            IPCMessages into.
        """
        if self._running:
            raise RuntimeError("Processing is already running")
        if not self._assignments or self._worker_class is None:
            raise RuntimeError("Must call configure() before start()")

        self._result_queue = Queue()
        self._shutdown_event = Event()
        self._processes = []

        for assignment in self._assignments:
            # Serialize chunks to plain dicts for pickling
            chunks_dicts = None
            if assignment.chunks:
                chunks_dicts = [asdict(c) for c in assignment.chunks]

            proc = Process(
                target=_worker_entry,
                args=(
                    self._worker_class,
                    assignment.stream_id,
                    assignment.video_paths,
                    self._result_queue,
                    self._shutdown_event,
                    self._config,
                    assignment.use_gpu,
                    assignment.preview_enabled,
                    chunks_dicts,
                ),
                daemon=True,
                name=f"stream-{assignment.stream_id}",
            )
            self._processes.append(proc)

        # Start all processes
        for proc in self._processes:
            proc.start()
            logger.info("Started process %s (pid=%s)", proc.name, proc.pid)

        self._running = True
        return self._result_queue

    def stop(self) -> None:
        """Gracefully stop all worker processes.

        Sets the shutdown event, waits up to _JOIN_TIMEOUT seconds for each
        process, then terminates any that have not exited.
        """
        if not self._running:
            return

        logger.info("Stopping %d worker processes...", len(self._processes))

        # Signal all workers to stop
        if self._shutdown_event is not None:
            self._shutdown_event.set()

        # Join with timeout
        for proc in self._processes:
            proc.join(timeout=_JOIN_TIMEOUT)

        # Terminate stragglers
        for proc in self._processes:
            if proc.is_alive():
                logger.warning(
                    "Terminating unresponsive process %s (pid=%s)",
                    proc.name,
                    proc.pid,
                )
                proc.terminate()
                proc.join(timeout=2.0)

        self._processes.clear()
        self._running = False
        logger.info("All worker processes stopped")

    # ── Properties ────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        """Whether worker processes are currently active."""
        return self._running

    @property
    def active_streams(self) -> int:
        """Number of worker processes still alive."""
        return sum(1 for p in self._processes if p.is_alive())

    @property
    def total_streams(self) -> int:
        """Total number of configured streams."""
        return len(self._assignments)
