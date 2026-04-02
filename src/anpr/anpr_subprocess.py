"""Multiprocessing worker for ANPR plate extraction.

Runs YOLO detection + ByteTrack tracking + PaddleOCR inside a child
process. Saves vehicle and plate crop images to disk, reads overlay
timestamps from the video, and pushes vehicle detection results back
to the main process via the IPC queue.

Follows the same pattern as ``src/intersection/intersection_subprocess.py``.
"""

from __future__ import annotations

import logging
import os
import re
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Any

import cv2
import numpy as np

from src.engine.base_worker import BaseVideoWorker

logger = logging.getLogger(__name__)

# Vehicle class IDs from COCO (car, motorcycle, bus, truck)
VEHICLE_CLASS_IDS = [2, 3, 5, 7]

# Direction detection constants
DIRECTION_HISTORY_LEN = 30
DIRECTION_MIN_FRAMES = 10
DIRECTION_THRESHOLD = 20

# Plate crop region: bottom portion of vehicle bbox
PLATE_CROP_TOP = 0.50      # start at 50% down
PLATE_CROP_BOTTOM = 1.0    # to bottom
PLATE_CROP_INSET = 0.10    # inset 10% from each side


def _add_seconds_to_timestr(time_str: str, seconds: float) -> str:
    """Add seconds to a HH:MM:SS time string, returning HH:MM:SS."""
    try:
        parts = time_str.split(":")
        h, m, s = int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0
        base = datetime(2000, 1, 1, h, m, s)
        result = base + timedelta(seconds=seconds)
        return result.strftime("%H:%M:%S")
    except (ValueError, IndexError):
        return time_str


class ANPRSubprocessWorker(BaseVideoWorker):
    """Worker process for ANPR plate extraction with image capture.

    Config keys:
        model_path (str):           YOLO model weights (default "yolov8n.pt")
        confidence (float):         Detection threshold (default 0.4)
        frame_skip (int):           Process every Nth frame (default 3)
        capture_zones (list):       Polygon zones for inclusion filtering
        exclusion_zones (list):     Polygon zones for exclusion filtering
        towards_label (str):        Label for towards-camera direction
        away_label (str):           Label for away-from-camera direction
        output_dir (str):           Temp directory for saving image crops
        corrections_path (str):     Path to ML feedback JSON file
        overlay_ocr_interval (int): Read overlay timestamp every N frames (default 30)
    """

    def _load_models(self) -> None:
        """Load YOLO, PaddleOCR, and OverlayOCR models."""
        from ultralytics import YOLO
        from src.anpr.plate_ocr import PlateOCR
        from src.common.overlay_ocr import OverlayOCR
        from src.anpr.ml_feedback import MLFeedbackStore

        model_path = self.config.get("model_path", "yolov8n.pt")
        device = "cuda:0" if self.use_gpu else "cpu"

        self._push_status(f"Loading YOLO model: {model_path}")
        self._model = YOLO(model_path)
        self._model.to(device)

        self._push_status("Loading PaddleOCR...")
        self._ocr = PlateOCR()

        self._push_status("Loading overlay OCR...")
        self._overlay_ocr = OverlayOCR()

        # Config
        self._confidence = self.config.get("confidence", 0.4)
        self._frame_skip = self.config.get("frame_skip", 3)
        self._capture_zones = self.config.get("capture_zones", [])
        self._exclusion_zones = self.config.get("exclusion_zones", [])
        self._towards_label = self.config.get("towards_label", "NB")
        self._away_label = self.config.get("away_label", "SB")
        self._overlay_interval = self.config.get("overlay_ocr_interval", 30)

        # Output directory for image crops
        base_output = self.config.get("output_dir", "")
        self._output_dir = os.path.join(base_output, f"stream_{self.stream_id}")
        os.makedirs(self._output_dir, exist_ok=True)

        # ML feedback corrections
        corrections_path = self.config.get("corrections_path", "")
        self._ml_feedback = MLFeedbackStore(corrections_path)

        # Tracker config
        tracker_config = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "bytetrack_traffic.yaml",
        )
        self._tracker_config = tracker_config if os.path.isfile(tracker_config) else "bytetrack.yaml"

        # Per-video state (reset in on_video_complete)
        self._track_history: dict[int, deque] = defaultdict(
            lambda: deque(maxlen=DIRECTION_HISTORY_LEN)
        )
        self._seen_tracks: dict[int, dict] = {}  # track_id -> best result so far
        self._crop_counter = 0

        # Overlay timestamp state
        self._last_overlay_time: str | None = None
        self._last_overlay_frame: int = -1

        self._push_status("All models loaded, ready to process")

    def process_frame(
        self,
        frame: Any,
        frame_num: int,
        video_info: dict,
    ) -> None:
        """Process a single frame: detect vehicles, crop, OCR plates."""
        fps = video_info.get("fps", 30.0)
        filename = video_info.get("filename", "")

        # Frame skip
        if frame_num % self._frame_skip != 0:
            return

        # ── Read overlay timestamp periodically ─────────────────────
        real_time = self._get_real_time(frame, frame_num, fps)

        # ── Run YOLO tracking ───────────────────────────────────────
        results = self._model.track(
            frame,
            classes=VEHICLE_CLASS_IDS,
            conf=self._confidence,
            tracker=self._tracker_config,
            persist=True,
            verbose=False,
        )

        has_tracks = (
            results
            and results[0].boxes is not None
            and results[0].boxes.id is not None
        )

        if not has_tracks:
            return

        boxes = results[0].boxes

        for i in range(len(boxes)):
            track_id = int(boxes.id[i])
            x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy().astype(int)
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

            # Direction detection
            direction = self._compute_direction(track_id, cx, cy)

            # Zone filtering
            if not self._check_zones(cx, cy):
                continue

            # ── Crop vehicle image ──────────────────────────────────
            h_frame, w_frame = frame.shape[:2]
            vx1 = max(0, int(x1))
            vy1 = max(0, int(y1))
            vx2 = min(w_frame, int(x2))
            vy2 = min(h_frame, int(y2))
            vehicle_crop = frame[vy1:vy2, vx1:vx2]

            # ── Crop plate region (bottom portion of vehicle bbox) ──
            bbox_h = vy2 - vy1
            bbox_w = vx2 - vx1
            plate_y1 = vy1 + int(bbox_h * PLATE_CROP_TOP)
            plate_y2 = vy1 + int(bbox_h * PLATE_CROP_BOTTOM)
            inset = int(bbox_w * PLATE_CROP_INSET)
            plate_x1 = max(0, vx1 + inset)
            plate_x2 = min(w_frame, vx2 - inset)

            # Fallback if crop too small
            if (plate_y2 - plate_y1) < 10 or (plate_x2 - plate_x1) < 20:
                plate_y1, plate_y2 = vy1, vy2
                plate_x1, plate_x2 = vx1, vx2

            plate_crop = frame[plate_y1:plate_y2, plate_x1:plate_x2]

            if plate_crop.size == 0 or vehicle_crop.size == 0:
                continue

            # ── OCR ─────────────────────────────────────────────────
            plate_text, ocr_conf = self._ocr.read(plate_crop)

            if not plate_text or len(plate_text) < 3:
                continue

            # Apply ML corrections
            confidence_pct = round(ocr_conf * 100, 1)
            plate_text = self._ml_feedback.apply_corrections(plate_text, confidence_pct)
            is_valid = self._ocr.validate_plate(plate_text)

            # ── Save crop images ────────────────────────────────────
            self._crop_counter += 1
            crop_prefix = f"{self._crop_counter:06d}_t{track_id}"

            vehicle_crop_path = os.path.join(
                self._output_dir, f"{crop_prefix}_vehicle.jpg"
            )
            plate_crop_path = os.path.join(
                self._output_dir, f"{crop_prefix}_plate.jpg"
            )

            try:
                cv2.imwrite(vehicle_crop_path, vehicle_crop,
                            [cv2.IMWRITE_JPEG_QUALITY, 85])
                cv2.imwrite(plate_crop_path, plate_crop,
                            [cv2.IMWRITE_JPEG_QUALITY, 90])
            except Exception as e:
                logger.warning("Failed to save crop: %s", e)
                vehicle_crop_path = ""
                plate_crop_path = ""

            # ── Check if this is a better reading for this track ────
            is_new_best = True
            if track_id in self._seen_tracks:
                prev = self._seen_tracks[track_id]
                if confidence_pct <= prev.get("confidence", 0):
                    is_new_best = False

            # Always push the result for the vehicle store
            result = {
                "type": "vehicle_detection",
                "track_id": track_id,
                "plate_text": plate_text,
                "confidence": confidence_pct,
                "is_valid": is_valid,
                "direction": direction,
                "real_time": real_time,
                "video_file": filename,
                "frame_num": frame_num,
                "vehicle_crop_path": vehicle_crop_path,
                "plate_crop_path": plate_crop_path,
                "source": "paddle",
                "is_new_best": is_new_best,
                "is_overlap": video_info.get("is_overlap", False),
            }

            if is_new_best:
                self._seen_tracks[track_id] = result

            self._push_result(result)

    # ── Timestamp OCR ───────────────────────────────────────────────

    def _get_real_time(self, frame: Any, frame_num: int, fps: float) -> str:
        """Get real timestamp from overlay OCR with interpolation.

        Reads the burned-in timestamp every N frames and interpolates
        between reads to avoid expensive OCR on every frame.
        """
        if frame_num % self._overlay_interval == 0:
            try:
                overlay = self._overlay_ocr.detect_from_frame(frame)
                ts = overlay.get("timestamp")
                if ts:
                    self._last_overlay_time = ts
                    self._last_overlay_frame = frame_num
            except Exception as e:
                logger.debug("Overlay OCR failed on frame %d: %s", frame_num, e)

        # Interpolate from last known timestamp
        if self._last_overlay_time and self._last_overlay_frame >= 0:
            delta_frames = frame_num - self._last_overlay_frame
            delta_sec = delta_frames / fps if fps > 0 else 0
            return _add_seconds_to_timestr(self._last_overlay_time, delta_sec)

        # Fallback: calculate from elapsed time
        elapsed_sec = frame_num / fps if fps > 0 else 0
        m = int(elapsed_sec) // 60
        s = int(elapsed_sec) % 60
        h = m // 60
        m = m % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    # ── Direction detection ─────────────────────────────────────────

    def _compute_direction(self, track_id: int, cx: int, cy: int) -> str:
        """Compute movement direction from centroid history."""
        self._track_history[track_id].append((cx, cy))

        history = self._track_history[track_id]
        if len(history) >= DIRECTION_MIN_FRAMES:
            old_cx, old_cy = history[-DIRECTION_MIN_FRAMES]
            dy = cy - old_cy
            if abs(dy) > DIRECTION_THRESHOLD:
                return self._towards_label if dy > 0 else self._away_label

        return ""

    # ── Zone filtering ──────────────────────────────────────────────

    def _check_zones(self, cx: int, cy: int) -> bool:
        """Check if centroid passes capture/exclusion zone filtering."""
        # Import here to avoid top-level PySide6 import in subprocess
        # The zone logic uses cv2.pointPolygonTest which is fine
        if self._capture_zones:
            in_capture = False
            for zone in self._capture_zones:
                pts = np.array(zone, dtype=np.float32)
                if cv2.pointPolygonTest(pts, (float(cx), float(cy)), False) >= 0:
                    in_capture = True
                    break
            if not in_capture:
                return False

        if self._exclusion_zones:
            for zone in self._exclusion_zones:
                pts = np.array(zone, dtype=np.float32)
                if cv2.pointPolygonTest(pts, (float(cx), float(cy)), False) >= 0:
                    return False

        return True

    # ── Video lifecycle ─────────────────────────────────────────────

    def on_video_complete(self, video_info: dict) -> None:
        """Reset tracker and per-video state between videos."""
        # Reset ByteTrack state
        try:
            if hasattr(self._model, "predictor") and hasattr(self._model.predictor, "trackers"):
                for tracker in self._model.predictor.trackers:
                    tracker.reset()
                logger.debug("ByteTrack reset for stream %d", self.stream_id)
        except Exception as e:
            logger.warning("Failed to reset tracker: %s", e)

        # Clear per-video state
        self._track_history.clear()
        self._seen_tracks.clear()
        self._last_overlay_time = None
        self._last_overlay_frame = -1

        self._push_status(
            f"Video complete: {video_info.get('filename', '?')}"
        )
