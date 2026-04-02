"""Background worker thread for midblock vehicle counting.

Processes multiple videos, supports multiple named count lines,
time filtering, and optional speed estimation.
Uses persist=True for all model.track() calls — tracker state is
reset between videos via tracker.reset() to avoid ID carry-over.
"""

import logging
import math
import os
import time as time_mod
from collections import defaultdict
from datetime import time, datetime, timedelta

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from src.counter.vehicle_classifier import (
    AustroadsClassifier,
    COCO_CAR,
    COCO_MOTORCYCLE,
    COCO_BUS,
    COCO_TRUCK,
    COCO_BICYCLE,
)
from src.common.utils import (
    parse_start_time,
    time_in_range,
    format_timestamp,
    compute_video_real_start,
    bgr_to_qimage,
    extract_filename,
    get_video_info,
    get_interval_key,
    get_realtime_interval_key,
)
from src.common.zone_widget import should_process_detection, draw_zones_on_frame

logger = logging.getLogger(__name__)

# Vehicle COCO class IDs to detect
VEHICLE_CLASSES = [COCO_BICYCLE, COCO_CAR, COCO_MOTORCYCLE, COCO_BUS, COCO_TRUCK]

# How often to send a preview frame to the UI (seconds)
UI_UPDATE_INTERVAL = 0.3

# Speed estimation constants
MAX_SPEED_KMH = 200
SPEED_SMOOTH_WINDOW = 30
MIN_SPEED_SAMPLES = 3

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


class CounterWorker(QThread):
    """Processes video files, counting vehicles crossing multiple lines."""

    progress = Signal(int)
    frame_processed = Signal(QImage, dict)
    finished = Signal(dict)
    error = Signal(str)
    status_update = Signal(str)
    video_started = Signal(int, int, str)

    def __init__(
        self,
        video_paths: list[str],
        count_lines: list[dict],
        model_path: str = "yolo11x.pt",
        confidence: float = 0.3,
        selected_classes: list[str] | None = None,
        frame_skip: int = 1,  # process every frame for best accuracy
        vision_classifier=None,
        time_filter: tuple[time, time] | None = None,
        video_start_time: str | None = None,
        speed_calibration=None,
        capture_zones: list | None = None,
        exclusion_zones: list | None = None,
        night_enhance: bool = False,
    ):
        super().__init__()
        self.video_paths = video_paths
        self.count_lines = count_lines
        self.model_path = model_path
        self.confidence = confidence
        self.selected_classes = selected_classes
        self.frame_skip = frame_skip
        self.vision_classifier = vision_classifier
        self.time_filter = time_filter
        self.video_start_time = video_start_time
        self.speed_calibration = speed_calibration
        self.capture_zones = capture_zones
        self.exclusion_zones = exclusion_zones
        self.night_enhance = night_enhance
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        try:
            self._process_videos()
        except Exception as e:
            logger.exception("Counter processing failed")
            self.error.emit(str(e))

    # ------------------------------------------------------------------
    # Main processing loop
    # ------------------------------------------------------------------

    def _process_videos(self):
        self.status_update.emit("Loading AI models...")

        from ultralytics import YOLO

        # Auto-select TensorRT engine if available
        from src.common.tensorrt_export import auto_select_model
        actual_model_path = auto_select_model(self.model_path)

        model = YOLO(actual_model_path)
        fallback_classifier = AustroadsClassifier()

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

        # Counting state (persists across all videos)
        state = self._init_counting_state()
        process_start = time_mod.time()
        frames_processed_total = 0

        for video_idx, video_path in enumerate(self.video_paths):
            if not self._running:
                break

            fps = video_fps_list[video_idx]
            frame_skip = self.frame_skip

            # Reset ByteTrack state between videos so IDs don't carry over.
            # On the first video the tracker hasn't been created yet, so skip.
            if video_idx > 0:
                self._reset_tracker(model)

            frames_processed_total = self._process_single_video(
                model=model,
                fallback_classifier=fallback_classifier,
                video_path=video_path,
                video_idx=video_idx,
                fps=fps,
                frame_skip=frame_skip,
                base_start=base_start,
                video_frame_counts=video_frame_counts,
                video_fps_list=video_fps_list,
                total_frames_all=total_frames_all,
                frames_processed_total=frames_processed_total,
                state=state,
                process_start=process_start,
                night_enhancer=night_enhancer,
            )

        # Build and emit final results
        self._emit_results(state, video_frame_counts, video_fps_list, process_start)

    # ------------------------------------------------------------------
    # Tracker management
    # ------------------------------------------------------------------

    @staticmethod
    def _reset_tracker(model):
        """Reset ByteTrack state between videos (clears all tracks, resets IDs).

        This preserves the registered callbacks (which have persist=True baked in)
        while clearing the actual tracking state so new videos start fresh.
        """
        try:
            if hasattr(model, "predictor") and hasattr(model.predictor, "trackers"):
                for tracker in model.predictor.trackers:
                    tracker.reset()
                logger.debug("Tracker reset for new video")
        except Exception as e:
            logger.warning("Failed to reset tracker: %s", e)

    # ------------------------------------------------------------------
    # Per-video processing
    # ------------------------------------------------------------------

    def _process_single_video(
        self,
        *,
        model,
        fallback_classifier,
        video_path: str,
        video_idx: int,
        fps: float,
        frame_skip: int,
        base_start,
        video_frame_counts,
        video_fps_list,
        total_frames_all,
        frames_processed_total: int,
        state: dict,
        process_start: float,
        night_enhancer=None,
    ) -> int:
        """Process one video file. Returns updated frames_processed_total."""

        filename = extract_filename(video_path)
        self.video_started.emit(video_idx, len(self.video_paths), filename)
        self.status_update.emit(
            f"Processing video {video_idx + 1}/{len(self.video_paths)}: {filename}"
        )

        video_real_start = compute_video_real_start(
            base_start, video_idx, video_frame_counts, video_fps_list
        )

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            self.error.emit(f"Cannot open video: {video_path}")
            return frames_processed_total

        frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        total_video_duration = video_frame_counts[video_idx] / fps if fps > 0 else 0

        # Reset per-video tracking state
        prev_centroids: dict[int, tuple[int, int]] = {}
        per_line_counted_ids = {line["label"]: set() for line in self.count_lines}
        track_speeds: dict[int, list[float]] = defaultdict(list) if state["speed_enabled"] else {}
        frame_num = 0
        last_ui_update = 0.0

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

            # Compute real-world time and apply time filter
            interval_key, skip_frame = self._compute_time_context(
                video_real_start, timestamp_sec
            )
            if skip_frame:
                frame_num += 1
                frames_processed_total += 1
                continue

            # Night enhancement — brighten dark frames before detection
            if night_enhancer is not None:
                frame = night_enhancer.enhance(frame)

            # Run YOLO tracking — ALWAYS persist=True.
            # On the first call the tracker auto-initialises internally.
            # Between videos we call tracker.reset() instead.
            results = model.track(
                frame,
                classes=VEHICLE_CLASSES,
                conf=self.confidence,
                tracker=TRACKER_CONFIG,
                persist=True,
                verbose=False,
            )

            # Process detections
            if results and results[0].boxes is not None and results[0].boxes.id is not None:
                self._process_detections(
                    boxes=results[0].boxes,
                    frame=frame,
                    frame_width=frame_width,
                    fps=fps,
                    frame_skip=frame_skip,
                    interval_key=interval_key,
                    fallback_classifier=fallback_classifier,
                    prev_centroids=prev_centroids,
                    per_line_counted_ids=per_line_counted_ids,
                    track_speeds=track_speeds,
                    state=state,
                )

            # Throttled UI preview
            now = time_mod.time()
            if now - last_ui_update >= UI_UPDATE_INTERVAL:
                last_ui_update = now
                self._emit_preview(
                    frame=frame,
                    results=results,
                    video_idx=video_idx,
                    timestamp_sec=timestamp_sec,
                    total_video_duration=total_video_duration,
                    per_line_counted_ids=per_line_counted_ids,
                    state=state,
                    process_start=process_start,
                    video_frame_counts=video_frame_counts,
                    video_fps_list=video_fps_list,
                )

            frame_num += 1
            frames_processed_total += 1

        cap.release()
        return frames_processed_total

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def _init_counting_state(self) -> dict:
        """Initialize counting state that persists across videos."""
        speed_enabled = (
            self.speed_calibration is not None
            and self.speed_calibration.enabled
            and self.speed_calibration.pixels_per_meter > 0
        )

        per_line_counts = {}
        per_line_intervals = {}
        for line in self.count_lines:
            label = line["label"]
            per_line_counts[label] = {"in": defaultdict(int), "out": defaultdict(int)}
            per_line_intervals[label] = defaultdict(
                lambda: defaultdict(lambda: {"in": 0, "out": 0})
            )

        return {
            "per_line_counts": per_line_counts,
            "per_line_intervals": per_line_intervals,
            "per_line_speeds": defaultdict(list) if speed_enabled else None,
            "speed_enabled": speed_enabled,
        }

    # ------------------------------------------------------------------
    # Detection processing
    # ------------------------------------------------------------------

    def _process_detections(
        self,
        *,
        boxes,
        frame,
        frame_width,
        fps,
        frame_skip,
        interval_key,
        fallback_classifier,
        prev_centroids,
        per_line_counted_ids,
        track_speeds,
        state,
    ):
        """Process all detected boxes in a single frame."""
        for i in range(len(boxes)):
            track_id = int(boxes.id[i])
            class_id = int(boxes.cls[i])
            x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy().astype(int)
            bbox_width = x2 - x1
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

            # Zone filtering
            if not should_process_detection(cx, cy, self.capture_zones or [], self.exclusion_zones or []):
                continue

            # Classify vehicle
            austroads_class = self._classify_vehicle(
                class_id, frame, x1, y1, x2, y2, bbox_width, frame_width,
                fallback_classifier,
            )
            if self.selected_classes and austroads_class not in self.selected_classes:
                continue

            # Speed estimation
            if state["speed_enabled"] and track_id in prev_centroids:
                self._update_speed(
                    track_id, cx, cy, prev_centroids, track_speeds, fps, frame_skip
                )

            # Line crossing detection
            if track_id in prev_centroids:
                self._check_line_crossings(
                    track_id, cx, cy, prev_centroids,
                    per_line_counted_ids, track_speeds,
                    austroads_class, interval_key, state,
                )

            prev_centroids[track_id] = (cx, cy)

    def _classify_vehicle(
        self, class_id, frame, x1, y1, x2, y2, bbox_width, frame_width,
        fallback_classifier,
    ) -> str:
        """Classify a detected vehicle into an Austroads class."""
        if self.vision_classifier is not None and class_id in (COCO_TRUCK, COCO_BUS):
            crop = frame[max(0, y1):y2, max(0, x1):x2]
            if crop.size > 0:
                result = self.vision_classifier.classify_crop(crop)
                return result["austroads_class"]
        bbox_height = y2 - y1
        frame_height = frame.shape[0]
        return fallback_classifier.classify(class_id, bbox_width, bbox_height, frame_width, frame_height)

    def _update_speed(self, track_id, cx, cy, prev_centroids, track_speeds, fps, frame_skip):
        """Update speed tracking for a vehicle."""
        prev_cx, prev_cy = prev_centroids[track_id]
        pixel_dist = math.sqrt((cx - prev_cx) ** 2 + (cy - prev_cy) ** 2)
        time_delta = frame_skip / fps

        if time_delta > 0 and pixel_dist > 1:
            speed_ms = (pixel_dist / self.speed_calibration.pixels_per_meter) / time_delta
            speed_kmh = speed_ms * 3.6
            if speed_kmh < MAX_SPEED_KMH:
                track_speeds[track_id].append(speed_kmh)
                if len(track_speeds[track_id]) > SPEED_SMOOTH_WINDOW:
                    track_speeds[track_id] = track_speeds[track_id][-SPEED_SMOOTH_WINDOW:]

    def _check_line_crossings(
        self, track_id, cx, cy, prev_centroids,
        per_line_counted_ids, track_speeds,
        austroads_class, interval_key, state,
    ):
        """Check if a vehicle has crossed any count lines."""
        prev_cx, prev_cy = prev_centroids[track_id]

        for line in self.count_lines:
            label = line["label"]
            if track_id in per_line_counted_ids[label]:
                continue

            lx1, ly1 = line["start"]
            lx2, ly2 = line["end"]
            prev_side = self._side_of_line(prev_cx, prev_cy, lx1, ly1, lx2, ly2)
            curr_side = self._side_of_line(cx, cy, lx1, ly1, lx2, ly2)

            crossed_in = prev_side > 0 and curr_side <= 0
            crossed_out = prev_side <= 0 and curr_side > 0

            if crossed_in or crossed_out:
                direction = "in" if crossed_in else "out"
                state["per_line_counts"][label][direction][austroads_class] += 1
                state["per_line_intervals"][label][interval_key][austroads_class][direction] += 1
                per_line_counted_ids[label].add(track_id)

                # Record crossing speed
                if (
                    state["speed_enabled"]
                    and track_id in track_speeds
                    and len(track_speeds[track_id]) >= MIN_SPEED_SAMPLES
                ):
                    recent = track_speeds[track_id][-SPEED_SMOOTH_WINDOW:]
                    avg_speed = sum(recent) / len(recent)
                    state["per_line_speeds"][label].append({
                        "speed_kmh": round(avg_speed, 1),
                        "austroads_class": austroads_class,
                        "direction": direction,
                        "interval": interval_key,
                    })

    # ------------------------------------------------------------------
    # Time helpers
    # ------------------------------------------------------------------

    def _compute_time_context(
        self, video_real_start, timestamp_sec
    ) -> tuple[str, bool]:
        """Compute interval key and whether to skip this frame based on time filter.

        Returns (interval_key, should_skip).
        """
        if video_real_start:
            real_dt = video_real_start + timedelta(seconds=timestamp_sec)

            if self.time_filter:
                start_t, end_t = self.time_filter
                if not time_in_range(real_dt.time(), start_t, end_t):
                    return "", True

            return get_realtime_interval_key(real_dt), False
        else:
            return get_interval_key(timestamp_sec), False

    # ------------------------------------------------------------------
    # UI preview
    # ------------------------------------------------------------------

    def _emit_preview(
        self, *, frame, results, video_idx, timestamp_sec,
        total_video_duration, per_line_counted_ids, state,
        process_start, video_frame_counts, video_fps_list,
    ):
        """Build and emit a preview frame with overlay annotations."""
        elapsed = time_mod.time() - process_start
        total_video_time = sum(
            video_frame_counts[i] / video_fps_list[i]
            for i in range(video_idx + 1)
        )
        speed_x = (total_video_time / elapsed) if elapsed > 0 else 0

        preview = frame.copy()

        # Draw capture/exclusion zones
        if self.capture_zones or self.exclusion_zones:
            preview = draw_zones_on_frame(preview, self.capture_zones or [], self.exclusion_zones or [])

        # Draw count lines
        for line in self.count_lines:
            color = line["color_bgr"]
            cv2.line(preview, line["start"], line["end"], color, 3)
            mx = (line["start"][0] + line["end"][0]) // 2
            my = (line["start"][1] + line["end"][1]) // 2
            cv2.putText(
                preview, line["label"],
                (mx - 40, my - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2,
            )

        # Grand total
        grand_total = self._compute_grand_total(state)

        # Draw detection boxes
        all_counted = set()
        for counted in per_line_counted_ids.values():
            all_counted.update(counted)

        if results and results[0].boxes is not None and results[0].boxes.id is not None:
            for i in range(len(results[0].boxes)):
                bx1, by1, bx2, by2 = results[0].boxes.xyxy[i].cpu().numpy().astype(int)
                tid = int(results[0].boxes.id[i])
                color = (0, 255, 0) if tid in all_counted else (255, 255, 0)
                cv2.rectangle(preview, (bx1, by1), (bx2, by2), color, 2)

        # Status overlay
        vid_label = f"  [{video_idx+1}/{len(self.video_paths)}]" if len(self.video_paths) > 1 else ""
        cv2.putText(
            preview,
            f"Vehicles: {grand_total}  |  {speed_x:.1f}x{vid_label}",
            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2,
        )
        time_pos = format_timestamp(timestamp_sec)
        total_dur_str = format_timestamp(total_video_duration)
        cv2.putText(
            preview,
            f"{time_pos} / {total_dur_str}",
            (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1,
        )

        qimg = bgr_to_qimage(preview)
        self.frame_processed.emit(qimg, {"grand_total": grand_total})

        self.status_update.emit(
            f"Processing at {speed_x:.1f}x speed  |  "
            f"Video {video_idx+1}/{len(self.video_paths)}  |  "
            f"Vehicles: {grand_total}"
        )

    # ------------------------------------------------------------------
    # Results compilation
    # ------------------------------------------------------------------

    def _compute_grand_total(self, state: dict) -> int:
        total = 0
        for label in state["per_line_counts"]:
            total += sum(state["per_line_counts"][label]["in"].values())
            total += sum(state["per_line_counts"][label]["out"].values())
        return total

    def _emit_results(self, state, video_frame_counts, video_fps_list, process_start):
        """Build and emit final results dict."""
        total_elapsed = time_mod.time() - process_start

        per_line_results = {}
        grand_total = 0

        for line in self.count_lines:
            label = line["label"]
            counts_in = dict(state["per_line_counts"][label]["in"])
            counts_out = dict(state["per_line_counts"][label]["out"])
            line_total = sum(counts_in.values()) + sum(counts_out.values())
            grand_total += line_total

            line_result = {
                "counts_in": counts_in,
                "counts_out": counts_out,
                "total_in": sum(counts_in.values()),
                "total_out": sum(counts_out.values()),
                "total": line_total,
                "intervals": {
                    k: {cls: dict(dirs) for cls, dirs in v.items()}
                    for k, v in sorted(state["per_line_intervals"][label].items())
                },
            }

            if state["speed_enabled"] and state["per_line_speeds"]:
                line_result["speeds"] = state["per_line_speeds"].get(label, [])

            per_line_results[label] = line_result

        total_duration = sum(
            video_frame_counts[i] / video_fps_list[i]
            for i in range(len(self.video_paths))
        )

        final_results = {
            "per_line": per_line_results,
            "grand_total": grand_total,
            "fps": video_fps_list[0] if video_fps_list else 25.0,
            "duration_sec": total_duration,
            "processing_time_sec": total_elapsed,
            "line_labels": [line["label"] for line in self.count_lines],
            "video_count": len(self.video_paths),
            "speed_enabled": state["speed_enabled"],
        }

        if self.vision_classifier is not None:
            final_results["vision_stats"] = self.vision_classifier.get_stats()

        self.progress.emit(100)
        speed = total_duration / total_elapsed if total_elapsed > 0 else 0
        self.status_update.emit(
            f"Complete — {grand_total} vehicles counted in "
            f"{total_elapsed:.0f}s ({speed:.1f}x speed) "
            f"across {len(self.video_paths)} video{'s' if len(self.video_paths) > 1 else ''}"
        )
        self.finished.emit(final_results)

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _side_of_line(
        px: int, py: int, lx1: int, ly1: int, lx2: int, ly2: int
    ) -> float:
        """Determine which side of a line a point is on (cross product)."""
        return (lx2 - lx1) * (py - ly1) - (ly2 - ly1) * (px - lx1)
