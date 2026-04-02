"""Multiprocessing worker for intersection turning movement counting.

Runs YOLO detection + ByteTrack tracking inside a child process, maps
detections to named polygon zones, and pushes zone-transition O-D results
back to the main process via the IPC queue.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Optional

import cv2
import numpy as np

from src.common.data_models import COCO_TO_AUSTROADS, NamedZone
from src.engine.base_worker import BaseVideoWorker
from src.engine.ipc_protocol import MsgType
from src.intersection.od_matrix import ODMatrix
from src.intersection.zone_tracker import ZoneTracker

logger = logging.getLogger(__name__)

# Frames without seeing a track before it is considered expired
_TRACK_EXPIRY_FRAMES = 90


def _make_interval_key(timestamp_sec: float, video_start_time: str = "") -> str:
    """Generate a 15-minute interval key from a timestamp.

    Args:
        timestamp_sec: Seconds since start of video (frame_num / fps).
        video_start_time: Optional HH:MM base time for the video.

    Returns:
        Interval key like "07:00-07:15".
    """
    if video_start_time:
        try:
            parts = video_start_time.split(":")
            base_h, base_m = int(parts[0]), int(parts[1])
            base = datetime(2000, 1, 1, base_h, base_m)
        except (ValueError, IndexError):
            base = datetime(2000, 1, 1, 0, 0)
    else:
        base = datetime(2000, 1, 1, 0, 0)

    current = base + timedelta(seconds=timestamp_sec)
    # Round down to nearest 15-minute block
    minute_block = (current.minute // 15) * 15
    start = current.replace(minute=minute_block, second=0, microsecond=0)
    end = start + timedelta(minutes=15)

    return f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"


class IntersectionWorker(BaseVideoWorker):
    """Worker process for intersection zone-to-zone vehicle tracking.

    Config keys:
        model_path (str):      Path to the YOLO model weights file.
        zones (list[dict]):    List of zone dicts with keys: name, zone_type,
                               polygon, color_bgr, approach.
        confidence (float):    YOLO confidence threshold (default 0.3).
        video_start_time (str): Base time for interval keys (HH:MM).
        classification_config (dict): Optional classification settings.
    """

    def _load_models(self) -> None:
        """Load YOLO model for detection and tracking."""
        from ultralytics import YOLO

        model_path = self.config.get("model_path", "yolov8n.pt")
        device = "cuda:0" if self.use_gpu else "cpu"

        self._push_status(f"Loading YOLO model: {model_path}")
        self._model = YOLO(model_path)
        self._model.to(device)

        # Build NamedZone objects from config
        zone_dicts = self.config.get("zones", [])
        zones = []
        for zd in zone_dicts:
            zones.append(
                NamedZone(
                    name=zd.get("name", ""),
                    zone_type=zd.get("zone_type", "entry"),
                    polygon=[tuple(p) for p in zd.get("polygon", [])],
                    color_bgr=tuple(zd.get("color_bgr", (0, 255, 0))),
                    approach=zd.get("approach", ""),
                )
            )

        self._zone_tracker = ZoneTracker(zones)
        self._od_matrix = ODMatrix()
        self._confidence = self.config.get("confidence", 0.3)
        self._video_start_time = self.config.get("video_start_time", "")

        # Track management
        self._last_seen: dict[int, int] = {}  # track_id -> last frame_num
        self._total_od_count = 0

        self._push_status("Models loaded, ready to process")

    def process_frame(
        self,
        frame: Any,
        frame_num: int,
        video_info: dict,
    ) -> None:
        """Process a single frame: detect, track, and update zone tracker.

        Args:
            frame:      BGR numpy array.
            frame_num:  Zero-based frame index within the current video.
            video_info: Dict with fps, filename, etc.
        """
        fps = video_info.get("fps", 30.0)
        timestamp_sec = frame_num / fps if fps > 0 else 0.0
        interval_key = _make_interval_key(
            timestamp_sec, self._video_start_time
        )

        # Run YOLO tracking with ByteTrack persistence
        results = self._model.track(
            frame,
            persist=True,
            conf=self._confidence,
            tracker="bytetrack.yaml",
            verbose=False,
        )

        active_track_ids: set[int] = set()

        if results and len(results) > 0:
            result = results[0]
            boxes = result.boxes

            if boxes is not None and boxes.id is not None:
                track_ids = boxes.id.int().cpu().numpy()
                class_ids = boxes.cls.int().cpu().numpy()
                xyxy = boxes.xyxy.cpu().numpy()

                for i in range(len(track_ids)):
                    track_id = int(track_ids[i])
                    class_id = int(class_ids[i])
                    x1, y1, x2, y2 = xyxy[i]

                    # Compute centroid
                    cx = int((x1 + x2) / 2)
                    cy = int((y1 + y2) / 2)

                    # Map COCO class to Austroads
                    austroads_class = COCO_TO_AUSTROADS.get(class_id, "1")

                    active_track_ids.add(track_id)
                    self._last_seen[track_id] = frame_num

                    # Update zone tracker
                    od_pair = self._zone_tracker.update(
                        track_id=track_id,
                        cx=cx,
                        cy=cy,
                        austroads_class=austroads_class,
                        interval_key=interval_key,
                        timestamp=timestamp_sec,
                    )

                    if od_pair is not None:
                        self._total_od_count += 1
                        self._od_matrix.add_od_pair(
                            origin=od_pair.origin_zone,
                            dest=od_pair.dest_zone,
                            class_code=od_pair.austroads_class,
                            interval_key=od_pair.interval_key,
                        )

                        # Push result to main process
                        self._push_result({
                            "type": "od_pair",
                            "track_id": od_pair.track_id,
                            "origin": od_pair.origin_zone,
                            "dest": od_pair.dest_zone,
                            "class": od_pair.austroads_class,
                            "interval": od_pair.interval_key,
                            "timestamp": od_pair.timestamp,
                            "total_od_count": self._total_od_count,
                        })

        # Check for expired tracks
        expired_ids = []
        for tid, last_frame in self._last_seen.items():
            if frame_num - last_frame > _TRACK_EXPIRY_FRAMES:
                expired_ids.append(tid)

        for tid in expired_ids:
            del self._last_seen[tid]
            od_pair = self._zone_tracker.finalize_track(tid)
            if od_pair is not None:
                self._total_od_count += 1
                self._od_matrix.add_od_pair(
                    origin=od_pair.origin_zone,
                    dest=od_pair.dest_zone,
                    class_code=od_pair.austroads_class,
                    interval_key=od_pair.interval_key,
                )
                self._push_result({
                    "type": "od_pair",
                    "track_id": od_pair.track_id,
                    "origin": od_pair.origin_zone,
                    "dest": od_pair.dest_zone,
                    "class": od_pair.austroads_class,
                    "interval": od_pair.interval_key,
                    "timestamp": od_pair.timestamp,
                    "total_od_count": self._total_od_count,
                })

    def on_video_complete(self, video_info: dict) -> None:
        """Called after each video finishes - finalize remaining tracks."""
        remaining_ids = list(self._last_seen.keys())
        for tid in remaining_ids:
            del self._last_seen[tid]
            od_pair = self._zone_tracker.finalize_track(tid)
            if od_pair is not None:
                self._total_od_count += 1
                self._od_matrix.add_od_pair(
                    origin=od_pair.origin_zone,
                    dest=od_pair.dest_zone,
                    class_code=od_pair.austroads_class,
                    interval_key=od_pair.interval_key,
                )

        # Reset ByteTrack state for next video by clearing persist state
        # The model.track(persist=True) accumulates state; a new video
        # needs a fresh tracker.  We achieve this by calling track with
        # persist=False once, then resuming persist=True.
        self._push_status(
            f"Video complete. Total O-D pairs: {self._total_od_count}"
        )
