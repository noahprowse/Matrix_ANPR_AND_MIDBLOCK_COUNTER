"""QThread bridge between the multiprocessing Queue and Qt signals.

Polls the shared result queue and re-emits each IPCMessage as a typed
Qt signal so that UI widgets can connect to them on the main thread.
"""

from __future__ import annotations

import logging
import queue
from multiprocessing import Queue
from typing import Optional

from PySide6.QtCore import QThread, Signal

from src.engine.ipc_protocol import IPCMessage, MsgType

logger = logging.getLogger(__name__)

# Polling interval in seconds (100 ms)
_POLL_TIMEOUT = 0.1


class MonitorBridge(QThread):
    """Reads IPCMessages from a multiprocessing.Queue and emits Qt signals.

    Signals:
        stream_progress(stream_id, overall_percent)
        stream_frame(stream_id, jpeg_bytes)
        stream_status(stream_id, status_text)
        stream_result(stream_id, result_dict)
        stream_finished(stream_id, payload_dict)
        stream_error(stream_id, error_message)
        all_finished(summary_dict)
        video_started(stream_id, filename)

    Parameters:
        result_queue:     The shared multiprocessing.Queue to poll.
        expected_streams: How many streams are expected to finish before
                          all_finished is emitted.
    """

    # ── Qt Signals ────────────────────────────────────────────────────
    stream_progress = Signal(int, int)       # stream_id, overall_percent
    stream_frame = Signal(int, object)       # stream_id, jpeg bytes
    stream_status = Signal(int, str)         # stream_id, text
    stream_result = Signal(int, dict)        # stream_id, result dict
    stream_finished = Signal(int, dict)      # stream_id, payload
    stream_error = Signal(int, str)          # stream_id, error message
    all_finished = Signal(dict)              # summary dict
    video_started = Signal(int, str)         # stream_id, filename

    def __init__(
        self,
        result_queue: Queue,
        expected_streams: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._queue = result_queue
        self._expected = expected_streams
        self._finished_ids: set[int] = set()
        self._stop_flag = False

    # ── Public API ────────────────────────────────────────────────────

    def stop(self) -> None:
        """Request the polling loop to exit cleanly."""
        self._stop_flag = True

    # ── Thread body ───────────────────────────────────────────────────

    def run(self) -> None:  # noqa: C901 (complexity acceptable for dispatcher)
        """Poll the queue and dispatch messages to Qt signals."""
        logger.info(
            "MonitorBridge started, expecting %d streams", self._expected
        )

        while not self._stop_flag:
            try:
                msg: IPCMessage = self._queue.get(timeout=_POLL_TIMEOUT)
            except (queue.Empty, EOFError):
                continue
            except Exception:
                if self._stop_flag:
                    break
                continue

            self._dispatch(msg)

            # Check if all streams are done
            if len(self._finished_ids) >= self._expected:
                self.all_finished.emit({
                    "total_streams": self._expected,
                    "finished_streams": len(self._finished_ids),
                })
                logger.info("All %d streams finished", self._expected)
                break

        logger.info("MonitorBridge stopped")

    # ── Internal dispatch ─────────────────────────────────────────────

    def _dispatch(self, msg: IPCMessage) -> None:
        """Route an IPCMessage to the correct Qt signal."""
        sid = msg.stream_id
        mt = msg.msg_type
        payload = msg.payload

        if mt == MsgType.PROGRESS:
            self.stream_progress.emit(sid, payload.get("overall_percent", 0))

        elif mt == MsgType.FRAME:
            self.stream_frame.emit(sid, payload.get("jpeg", b""))

        elif mt == MsgType.STATUS:
            self.stream_status.emit(sid, payload.get("text", ""))

        elif mt == MsgType.RESULT:
            self.stream_result.emit(sid, payload)

        elif mt == MsgType.FINISHED:
            self._finished_ids.add(sid)
            self.stream_finished.emit(sid, payload)

        elif mt == MsgType.ERROR:
            self.stream_error.emit(sid, payload.get("message", "Unknown error"))

        elif mt == MsgType.HEARTBEAT:
            pass  # Heartbeats are silently consumed

        elif mt == MsgType.VIDEO_STARTED:
            self.video_started.emit(sid, payload.get("filename", ""))

        else:
            logger.warning("Unknown MsgType %s from stream %d", mt, sid)
