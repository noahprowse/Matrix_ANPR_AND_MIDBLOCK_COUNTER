"""Background worker thread for ANPR video processing.

Supports multiple video files processed sequentially with
cross-video plate deduplication and time filtering.
Reads every frame via cap.read() for codec reliability, but only
processes every Nth frame (frame_skip=3) for detection.

Uses BoT-SORT tracking to determine direction of travel, optional
capture/exclusion zone filtering, Claude plate validation, and
Azure Blob Storage uploads.
"""

import logging
import os
from collections import defaultdict, deque
from datetime import time, timedelta

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from src.anpr.plate_detector import PlateDetector
from src.anpr.plate_ocr import PlateOCR
from src.common.utils import (
    parse_start_time,
    time_in_range,
    format_timestamp,
    compute_video_real_start,
    bgr_to_qimage,
    extract_filename,
    get_video_info,
)
from src.common.zone_widget import should_process_detection

logger = logging.getLogger(__name__)

# Custom tracker config — prefer BoT-SORT for fewer ID switches
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BOTSORT_CONFIG = os.path.join(_PROJECT_ROOT, "botsort_traffic.yaml")
_BYTETRACK_CONFIG = os.path.join(_PROJECT_ROOT, "bytetrack_traffic.yaml")

if os.path.isfile(_BOTSORT_CONFIG):
    TRACKER_CONFIG = _BOTSORT_CONFIG
elif os.path.isfile(_BYTETRACK_CONFIG):
    TRACKER_CONFIG = _BYTETRACK_CONFIG
else:
    TRACKER_CONFIG = "botsort.yaml"

# Direction detection constants
DIRECTION_HISTORY_LEN = 30  # frames of centroid history to keep
DIRECTION_MIN_FRAMES = 10   # minimum history before computing direction
DIRECTION_THRESHOLD = 20    # minimum pixel displacement to assign direction


class ANPRWorker(QThread):
    """Processes one or more video files, detecting and reading license plates."""

    progress = Signal(int)
    frame_processed = Signal(QImage, list)
    plate_found = Signal(dict)
    finished = Signal(list)
    error = Signal(str)
    status_update = Signal(str)
    video_started = Signal(int, int, str)

    def __init__(
        self,
        video_paths: list[str],
        model_path: str = "yolo11x.pt",
        confidence: float = 0.4,
        time_filter: tuple[time, time] | None = None,
        video_start_time: str | None = None,
        capture_zones: list | None = None,
        exclusion_zones: list | None = None,
        towards_label: str = "Towards",
        away_label: str = "Away",
        claude_validator=None,  # ClaudePlateValidator instance
        blob_storage=None,  # ANPRBlobStorage instance
        night_enhance: bool = False,
    ):
        super().__init__()
        self.video_paths = video_paths
        self.model_path = model_path
        self.confidence = confidence
        self.time_filter = time_filter
        self.video_start_time = video_start_time
        self.capture_zones = capture_zones or []
        self.exclusion_zones = exclusion_zones or []
        self.towards_label = towards_label
        self.away_label = away_label
        self.claude_validator = claude_validator
        self.blob_storage = blob_storage
        self.night_enhance = night_enhance
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        try:
            self._process_videos()
        except Exception as e:
            logger.exception("ANPR processing failed")
            self.error.emit(str(e))

    # ------------------------------------------------------------------
    # Tracker management
    # ------------------------------------------------------------------

    @staticmethod
    def _reset_tracker(model):
        """Reset ByteTrack state between videos (clears all tracks, resets IDs)."""
        try:
            if hasattr(model, "predictor") and hasattr(model.predictor, "trackers"):
                for tracker in model.predictor.trackers:
                    tracker.reset()
                logger.debug("Tracker reset for new video")
        except Exception as e:
            logger.warning("Failed to reset tracker: %s", e)

    # ------------------------------------------------------------------
    # Direction detection
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_direction(
        track_id: int,
        cx: int,
        cy: int,
        track_history: dict[int, deque],
        towards_label: str,
        away_label: str,
    ) -> str:
        """Compute movement direction from centroid history.

        Returns towards_label if moving down (towards camera),
        away_label if moving up (away from camera), or "" if
        insufficient history or movement below threshold.
        """
        track_history[track_id].append((cx, cy))

        if len(track_history[track_id]) >= DIRECTION_MIN_FRAMES:
            old_cx, old_cy = track_history[track_id][-DIRECTION_MIN_FRAMES]
            dy = cy - old_cy
            if abs(dy) > DIRECTION_THRESHOLD:
                return towards_label if dy > 0 else away_label

        return ""

    # ------------------------------------------------------------------
    # Main processing loop
    # ------------------------------------------------------------------

    def _process_videos(self):
        self.status_update.emit("Loading AI models...")

        # Auto-select TensorRT engine if available
        from src.common.tensorrt_export import auto_select_model
        actual_model_path = auto_select_model(self.model_path)

        detector = PlateDetector(model_path=actual_model_path, confidence=self.confidence)
        ocr = PlateOCR()

        # Load the tracking model (separate from detector's inference model)
        from ultralytics import YOLO
        from src.anpr.plate_detector import VEHICLE_CLASS_IDS

        track_model = YOLO(actual_model_path)

        # Night enhancement
        night_enhancer = None
        if self.night_enhance:
            from src.common.night_enhance import NightEnhancer
            night_enhancer = NightEnhancer(auto_detect=True)
            self.status_update.emit("Night enhancement enabled (auto-detect)")

        # Pre-compute video metadata
        video_meta = [get_video_info(p) for p in self.video_paths]
        video_frame_counts = [m["frames"] for m in video_meta]
        video_fps_list = [m["fps"] for m in video_meta]
        total_frames_all = sum(video_frame_counts)

        base_start = parse_start_time(self.video_start_time)

        seen_plates: dict[str, dict] = {}
        frames_processed_total = 0

        for video_idx, video_path in enumerate(self.video_paths):
            if not self._running:
                break

            filename = extract_filename(video_path)
            self.video_started.emit(video_idx, len(self.video_paths), filename)
            self.status_update.emit(
                f"Processing video {video_idx + 1}/{len(self.video_paths)}: {filename}"
            )

            # Reset ByteTrack state between videos so IDs don't carry over.
            if video_idx > 0:
                self._reset_tracker(track_model)

            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                self.error.emit(f"Cannot open video: {video_path}")
                continue

            fps = video_fps_list[video_idx]
            frame_skip = 3  # Process every 3rd frame
            frame_num = 0

            video_real_start = compute_video_real_start(
                base_start, video_idx, video_frame_counts, video_fps_list
            )

            # Per-video tracking state
            track_history: dict[int, deque] = defaultdict(
                lambda: deque(maxlen=DIRECTION_HISTORY_LEN)
            )

            while self._running and cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                # Skip frames we don't need to process
                if frame_num % frame_skip != 0:
                    frame_num += 1
                    frames_processed_total += 1
                    continue

                # Progress
                if total_frames_all > 0:
                    pct = int((frames_processed_total / total_frames_all) * 100)
                    self.progress.emit(min(pct, 100))

                timestamp_sec = frame_num / fps
                time_str = format_timestamp(timestamp_sec)

                # Real-world time + filtering
                real_time_str = None
                if video_real_start:
                    real_dt = video_real_start + timedelta(seconds=timestamp_sec)
                    real_time_str = real_dt.strftime("%H:%M:%S")

                    if self.time_filter:
                        start_t, end_t = self.time_filter
                        if not time_in_range(real_dt.time(), start_t, end_t):
                            frame_num += 1
                            frames_processed_total += 1
                            continue

                # Night enhancement — brighten dark frames before detection
                if night_enhancer is not None:
                    frame = night_enhancer.enhance(frame)

                # Run YOLO tracking with BoT-SORT (persist=True).
                results = track_model.track(
                    frame,
                    classes=list(VEHICLE_CLASS_IDS),
                    conf=self.confidence,
                    tracker=TRACKER_CONFIG,
                    persist=True,
                    verbose=False,
                )

                frame_results = []

                has_tracks = (
                    results
                    and results[0].boxes is not None
                    and results[0].boxes.id is not None
                )

                if has_tracks:
                    boxes = results[0].boxes

                    for i in range(len(boxes)):
                        track_id = int(boxes.id[i])
                        x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy().astype(int)
                        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

                        # Compute direction of travel
                        direction = self._compute_direction(
                            track_id, cx, cy, track_history,
                            self.towards_label, self.away_label,
                        )

                        # Zone filtering: skip detections outside valid zones
                        if not should_process_detection(
                            cx, cy, self.capture_zones, self.exclusion_zones
                        ):
                            # Still draw the box but skip OCR
                            cv2.rectangle(frame, (x1, y1), (x2, y2), (128, 128, 128), 1)
                            continue

                        # Extract plate region and run OCR
                        det_bbox = (int(x1), int(y1), int(x2), int(y2))
                        plate_img = detector.crop_plate(frame, det_bbox)
                        plate_text, ocr_conf = ocr.read(plate_img)

                        if plate_text and len(plate_text) >= 3:
                            is_valid = ocr.validate_plate(plate_text)
                            claude_validated = False

                            # Claude validation for low-confidence or invalid plates
                            if self.claude_validator is not None:
                                if self.claude_validator.should_validate(ocr_conf, is_valid):
                                    try:
                                        claude_result = self.claude_validator.validate_plate(
                                            plate_img, plate_text, ocr_conf
                                        )
                                        if (
                                            claude_result["plate"]
                                            and len(claude_result["plate"]) >= 3
                                            and claude_result["plate"] != "UNREADABLE"
                                        ):
                                            plate_text = claude_result["plate"]
                                            ocr_conf = claude_result["confidence"]
                                            is_valid = ocr.validate_plate(plate_text)
                                            claude_validated = True
                                    except Exception as exc:
                                        logger.warning(
                                            "Claude validation failed: %s", exc
                                        )

                            result = {
                                "plate": plate_text,
                                "time": time_str,
                                "real_time": real_time_str or time_str,
                                "timestamp_sec": timestamp_sec,
                                "confidence": round(ocr_conf * 100, 1),
                                "frame": frame_num,
                                "bbox": det_bbox,
                                "valid": is_valid,
                                "video_file": filename,
                                "direction": direction,
                            }
                            frame_results.append(result)

                            # Deduplication: emit only new or higher-confidence
                            if (
                                plate_text not in seen_plates
                                or ocr_conf > seen_plates[plate_text]["confidence"] / 100
                            ):
                                seen_plates[plate_text] = result
                                self.plate_found.emit(result)

                            # Upload to blob storage
                            if self.blob_storage is not None:
                                try:
                                    self.blob_storage.upload_plate_result(
                                        plate_img=plate_img,
                                        plate_text=plate_text,
                                        confidence=round(ocr_conf * 100, 1),
                                        timestamp_str=real_time_str or time_str,
                                        video_file=filename,
                                        direction=direction,
                                        valid_format=is_valid,
                                        claude_validated=claude_validated,
                                    )
                                except Exception as exc:
                                    logger.warning(
                                        "Blob storage upload failed: %s", exc
                                    )

                        # Draw detection boxes on preview
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
                        label_parts = []
                        if plate_text:
                            label_parts.append(plate_text)
                        if direction:
                            label_parts.append(direction)
                        label_str = " ".join(label_parts)
                        if label_str:
                            cv2.putText(
                                frame, label_str,
                                (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                                (0, 255, 0), 2,
                            )

                # Emit frame for preview
                qimg = bgr_to_qimage(frame)
                self.frame_processed.emit(qimg, frame_results)

                frame_num += 1
                frames_processed_total += 1

            cap.release()

        # Final results
        all_results = sorted(
            seen_plates.values(), key=lambda r: r.get("real_time", r["time"])
        )
        self.progress.emit(100)
        self.status_update.emit(
            f"Complete — {len(all_results)} unique plates detected "
            f"across {len(self.video_paths)} video{'s' if len(self.video_paths) > 1 else ''}"
        )
        self.finished.emit(all_results)
