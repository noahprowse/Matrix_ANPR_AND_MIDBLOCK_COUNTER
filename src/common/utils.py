"""Shared utility functions for ANPR and Counter modules."""

import cv2
import numpy as np
from datetime import time, datetime, timedelta

from PySide6.QtGui import QImage


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def parse_start_time(time_str: str | None) -> datetime | None:
    """Parse 'HH:MM:SS' or 'HH:MM' into a datetime for today."""
    if not time_str:
        return None
    parts = time_str.split(":")
    if len(parts) < 2:
        return None
    try:
        h, m = int(parts[0]), int(parts[1])
        s = int(parts[2]) if len(parts) >= 3 else 0
        return datetime.today().replace(hour=h, minute=m, second=s, microsecond=0)
    except (ValueError, IndexError):
        return None


def time_in_range(t: time, start: time, end: time) -> bool:
    """Check if *t* falls within [start, end], supporting overnight ranges."""
    if start <= end:
        return start <= t <= end
    # Overnight range (e.g. 22:00 → 06:00)
    return t >= start or t <= end


def format_timestamp(seconds: float) -> str:
    """Convert seconds into 'HH:MM:SS' string."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_duration(seconds: float) -> str:
    """Human-friendly duration string ('1h 05m' or '3m 20s')."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m {s:02d}s"


def get_interval_key(timestamp_sec: float) -> str:
    """Build a 15-minute interval key from video-relative seconds."""
    total_minutes = int(timestamp_sec // 60)
    interval_start = (total_minutes // 15) * 15
    h_start = interval_start // 60
    m_start = interval_start % 60
    h_end = (interval_start + 15) // 60
    m_end = (interval_start + 15) % 60
    return f"{h_start:02d}:{m_start:02d}-{h_end:02d}:{m_end:02d}"


def get_realtime_interval_key(dt: datetime) -> str:
    """Build a 15-minute interval key from a real-world datetime."""
    h = dt.hour
    m = dt.minute
    interval_start = (m // 15) * 15
    interval_end = interval_start + 15
    h_end = h + (interval_end // 60)
    m_end = interval_end % 60
    return f"{h:02d}:{interval_start:02d}-{h_end:02d}:{m_end:02d}"


# ---------------------------------------------------------------------------
# Video helpers
# ---------------------------------------------------------------------------

def compute_frame_skip(fps: float, target_fps: float = 10.0) -> int:
    """Auto-calculate frame skip so we process ~target_fps frames/sec of video.

    For 25 fps video → skip 2  (process ~12.5 fps)
    For 30 fps video → skip 3  (process ~10 fps)
    For 60 fps video → skip 6  (process ~10 fps)
    """
    if fps <= 0:
        return 2
    skip = max(1, round(fps / target_fps))
    return skip


def get_video_info(path: str) -> dict:
    """Return basic metadata for a video file."""
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return {"frames": 0, "fps": 25.0, "duration": 0, "width": 0, "height": 0}
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return {
        "frames": frames,
        "fps": fps,
        "duration": frames / fps if fps > 0 else 0,
        "width": width,
        "height": height,
    }


def compute_video_real_start(
    base_start: datetime | None,
    video_idx: int,
    video_frame_counts: list[int],
    video_fps_list: list[float],
) -> datetime | None:
    """Compute the real-world start time for a specific video index."""
    if base_start is None:
        return None
    if video_idx == 0:
        return base_start
    prev_duration = sum(
        video_frame_counts[i] / video_fps_list[i] for i in range(video_idx)
    )
    return base_start + timedelta(seconds=prev_duration)


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

def bgr_to_qimage(frame: np.ndarray) -> QImage:
    """Convert a BGR OpenCV frame to a QImage (RGB888), making a deep copy."""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    return QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()


def extract_filename(path: str) -> str:
    """Extract the file name from a full path (cross-platform)."""
    return path.replace("\\", "/").rsplit("/", 1)[-1]
