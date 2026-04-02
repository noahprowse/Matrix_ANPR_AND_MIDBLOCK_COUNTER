"""Multiprocessing worker for midblock vehicle counting.

Runs YOLO detection + BoT-SORT tracking inside a child process, classifies
vehicles by Austroads class, detects line crossings, and pushes results
back to the main process via the IPC queue.
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import cv2

from src.common.zone_widget import should_process_detection
from src.counter.vehicle_classifier import (
    AustroadsClassifier,
    COCO_CAR,
    COCO_MOTORCYCLE,
    COCO_BUS,
    COCO_TRUCK,
    COCO_BICYCLE,
)
from src.engine.base_worker import BaseVideoWorker

logger = logging.getLogger(__name__)

VEHICLE_CLASSES = [COCO_BICYCLE, COCO_CAR, COCO_MOTORCYCLE, COCO_BUS, COCO_TRUCK]

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BOTSORT_CONFIG = os.path.join(_PROJECT_ROOT, "botsort_traffic.yaml")
_BYTETRACK_CONFIG = os.path.join(_PROJECT_ROOT, "bytetrack_traffic.yaml")

if os.path.isfile(_BOTSORT_CONFIG):
    TRACKER_CONFIG = _BOTSORT_CONFIG
elif os.path.isfile(_BYTETRACK_CONFIG):
    TRACKER_CONFIG = _BYTETRACK_CONFIG
else:
    TRACKER_CONFIG = "botsort.yaml"


def _make_interval_key(timestamp_sec: float, video_start_time: str = "") -> str:
    """Generate a 15-minute interval key from a timestamp."""
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
    minute_block = (current.minute // 15) * 15
    start = current.replace(minute=minute_block, second=0, microsecond=0)
    end = start + timedelta(minutes=15)
    return f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"


def _side_of_line(px, py, lx1, ly1, lx2, ly2) -> float:
    """Determine which side of a line a point is on (cross product)."""
    return (lx2 - lx1) * (py - ly1) - (ly2 - ly1) * (px - lx1)


class CounterSubprocessWorker(BaseVideoWorker):
    """Worker process for midblock vehicle counting with line crossings.

    Config keys:
        model_path (str):         Path to YOLO weights.
        count_lines (list[dict]): Lines with start, end, label, color_bgr.
        selected_classes (list):  Austroads classes to count (None = all).
        confidence (float):       YOLO confidence threshold.
        video_start_time (str):   Base time for intervals (HH:MM).
        capture_zones (list):     Optional capture zone polygons.
        exclusion_zones (list):   Optional exclusion zone polygons.
    """

    def _load_models(self) -> None:
        from ultralytics import YOLO

        model_path = self.config.get("model_path", "yolo11x.pt")
        device = "cuda:0" if self.use_gpu else "cpu"

        self._push_status(f"Loading YOLO model: {model_path}")
        self._model = YOLO(model_path)
        self._model.to(device)

        self._classifier = AustroadsClassifier()
        self._count_lines = self.config.get("count_lines", [])
        self._selected_classes = self.config.get("selected_classes")
        self._confidence = self.config.get("confidence", 0.3)
        self._video_start_time = self.config.get("video_start_time", "")
        self._capture_zones = self.config.get("capture_zones") or []
        self._exclusion_zones = self.config.get("exclusion_zones") or []

        # Per-video tracking state (reset between videos)
        self._prev_centroids: dict[int, tuple[int, int]] = {}
        self._per_line_counted_ids: dict[str, set] = {
            line["label"]: set() for line in self._count_lines
        }
        self._total_count = 0

        self._push_status("Models loaded, ready to process")

    def process_frame(
        self, frame: Any, frame_num: int, video_info: dict,
    ) -> None:
        fps = video_info.get("fps", 30.0)
        # Use absolute frame number relative to video start for timestamp
        abs_frame = frame_num - video_info.get("start_frame", 0)
        timestamp_sec = abs_frame / fps if fps > 0 else 0.0
        interval_key = _make_interval_key(timestamp_sec, self._video_start_time)
        frame_width = video_info.get("width", frame.shape[1])
        is_overlap = video_info.get("is_overlap", False)

        results = self._model.track(
            frame,
            classes=VEHICLE_CLASSES,
            conf=self._confidence,
            tracker=TRACKER_CONFIG,
            persist=True,
            verbose=False,
        )

        if not (results and results[0].boxes is not None and results[0].boxes.id is not None):
            return

        boxes = results[0].boxes
        for i in range(len(boxes)):
            track_id = int(boxes.id[i])
            class_id = int(boxes.cls[i])
            x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy().astype(int)
            bbox_width = x2 - x1
            bbox_height = y2 - y1
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

            # Zone filtering
            if not should_process_detection(
                cx, cy, self._capture_zones, self._exclusion_zones
            ):
                continue

            # Classify vehicle
            frame_height = frame.shape[0]
            austroads_class = self._classifier.classify(
                class_id, bbox_width, bbox_height, frame_width, frame_height
            )
            if self._selected_classes and austroads_class not in self._selected_classes:
                continue

            # Line crossing detection
            if track_id in self._prev_centroids and not is_overlap:
                prev_cx, prev_cy = self._prev_centroids[track_id]

                for line in self._count_lines:
                    label = line["label"]
                    if track_id in self._per_line_counted_ids[label]:
                        continue

                    lx1, ly1 = line["start"]
                    lx2, ly2 = line["end"]
                    prev_side = _side_of_line(prev_cx, prev_cy, lx1, ly1, lx2, ly2)
                    curr_side = _side_of_line(cx, cy, lx1, ly1, lx2, ly2)

                    crossed_in = prev_side > 0 and curr_side <= 0
                    crossed_out = prev_side <= 0 and curr_side > 0

                    if crossed_in or crossed_out:
                        direction = "in" if crossed_in else "out"
                        self._per_line_counted_ids[label].add(track_id)
                        self._total_count += 1

                        self._push_result({
                            "type": "line_crossing",
                            "line_label": label,
                            "direction": direction,
                            "austroads_class": austroads_class,
                            "interval_key": interval_key,
                            "track_id": track_id,
                            "total_count": self._total_count,
                        })

            self._prev_centroids[track_id] = (cx, cy)

    def on_video_complete(self, video_info: dict) -> None:
        """Reset per-video tracking state."""
        self._prev_centroids.clear()
        self._per_line_counted_ids = {
            line["label"]: set() for line in self._count_lines
        }

        # Reset ByteTrack state
        try:
            if hasattr(self._model, "predictor") and hasattr(self._model.predictor, "trackers"):
                for tracker in self._model.predictor.trackers:
                    tracker.reset()
        except Exception as e:
            logger.warning("Failed to reset tracker: %s", e)

        self._push_status(
            f"Video complete. Total vehicles: {self._total_count}"
        )
