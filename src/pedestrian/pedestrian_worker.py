"""Background worker thread for pedestrian counting.

Processes multiple videos, counts pedestrians crossing named count lines
using YOLO detection + BoT-SORT tracking. Simplified version of the
vehicle counter worker — no Austroads classification, no speed estimation.
"""

import logging
import os
import time as time_mod
from collections import defaultdict
from datetime import time, timedelta

import cv2
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

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

# COCO class ID for person
COCO_PERSON = 0

# How often to send a preview frame to the UI (seconds)
UI_UPDATE_INTERVAL = 0.3

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


class PedestrianWorker(QThread):
    """Processes video files, counting pedestrians crossing multiple lines."""

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
        frame_skip: int = 1,
        time_filter: tuple[time, time] | None = None,
        video_start_time: str | None = None,
        capture_zones: list | None = None,
        exclusion_zones: list | None = None,
    ):
        super().__init__()
        self.video_paths = video_paths
        self.count_lines = count_lines
        self.model_path = model_path
        self.confidence = confidence
        self.frame_skip = frame_skip
        self.time_filter = time_filter
        self.video_start_time = video_start_time
        self.capture_zones = capture_zones
        self.exclusion_zones = exclusion_zones
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        try:
            self._process_videos()
        except Exception as e:
            logger.exception("Pedestrian counting failed")
            self.error.emit(str(e))

    # ------------------------------------------------------------------
    # Main processing loop
    # ------------------------------------------------------------------

    def _process_videos(self):
        self.status_update.emit("Loading AI models...")

        from ultralytics import YOLO
        from src.common.tensorrt_export import auto_select_model

        actual_model_path = auto_select_model(self.model_path)
        model = YOLO(actual_model_path)

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

            # Reset tracker between videos
            if video_idx > 0:
                self._reset_tracker(model)

            frames_processed_total = self._process_single_video(
                model=model,
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
            )

        self._emit_results(state, video_frame_counts, video_fps_list, process_start)

    # ------------------------------------------------------------------
    # Tracker management
    # ------------------------------------------------------------------

    @staticmethod
    def _reset_tracker(model):
        try:
            if hasattr(model, "predictor") and hasattr(model.predictor, "trackers"):
                for tracker in model.predictor.trackers:
                    tracker.reset()
        except Exception as e:
            logger.warning("Failed to reset tracker: %s", e)

    # ------------------------------------------------------------------
    # Per-video processing
    # ------------------------------------------------------------------

    def _process_single_video(
        self,
        *,
        model,
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
    ) -> int:
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

        total_video_duration = video_frame_counts[video_idx] / fps if fps > 0 else 0

        # Per-video tracking state
        prev_centroids: dict[int, tuple[int, int]] = {}
        per_line_counted_ids = {line["label"]: set() for line in self.count_lines}
        frame_num = 0
        last_ui_update = 0.0

        while self._running and cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            if frame_num % frame_skip != 0:
                frame_num += 1
                frames_processed_total += 1
                continue

            if total_frames_all > 0:
                pct = int((frames_processed_total / total_frames_all) * 100)
                self.progress.emit(min(pct, 100))

            timestamp_sec = frame_num / fps

            interval_key, skip_frame = self._compute_time_context(
                video_real_start, timestamp_sec
            )
            if skip_frame:
                frame_num += 1
                frames_processed_total += 1
                continue

            # Run YOLO tracking — detect only persons
            results = model.track(
                frame,
                classes=[COCO_PERSON],
                conf=self.confidence,
                tracker=TRACKER_CONFIG,
                persist=True,
                verbose=False,
            )

            # Process detections
            if results and results[0].boxes is not None and results[0].boxes.id is not None:
                self._process_detections(
                    boxes=results[0].boxes,
                    interval_key=interval_key,
                    prev_centroids=prev_centroids,
                    per_line_counted_ids=per_line_counted_ids,
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
        per_line_counts = {}
        per_line_intervals = {}
        for line in self.count_lines:
            label = line["label"]
            per_line_counts[label] = {"in": 0, "out": 0}
            per_line_intervals[label] = defaultdict(lambda: {"in": 0, "out": 0})

        return {
            "per_line_counts": per_line_counts,
            "per_line_intervals": per_line_intervals,
        }

    # ------------------------------------------------------------------
    # Detection processing
    # ------------------------------------------------------------------

    def _process_detections(
        self, *, boxes, interval_key, prev_centroids, per_line_counted_ids, state,
    ):
        for i in range(len(boxes)):
            track_id = int(boxes.id[i])
            x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy().astype(int)
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

            # Zone filtering
            if not should_process_detection(
                cx, cy, self.capture_zones or [], self.exclusion_zones or []
            ):
                continue

            # Line crossing detection
            if track_id in prev_centroids:
                self._check_line_crossings(
                    track_id, cx, cy, prev_centroids,
                    per_line_counted_ids, interval_key, state,
                )

            prev_centroids[track_id] = (cx, cy)

    def _check_line_crossings(
        self, track_id, cx, cy, prev_centroids,
        per_line_counted_ids, interval_key, state,
    ):
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
                state["per_line_counts"][label][direction] += 1
                state["per_line_intervals"][label][interval_key][direction] += 1
                per_line_counted_ids[label].add(track_id)

    # ------------------------------------------------------------------
    # Time helpers
    # ------------------------------------------------------------------

    def _compute_time_context(self, video_real_start, timestamp_sec) -> tuple[str, bool]:
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
        elapsed = time_mod.time() - process_start
        total_video_time = sum(
            video_frame_counts[i] / video_fps_list[i]
            for i in range(video_idx + 1)
        )
        speed_x = (total_video_time / elapsed) if elapsed > 0 else 0

        preview = frame.copy()

        # Draw capture/exclusion zones
        if self.capture_zones or self.exclusion_zones:
            preview = draw_zones_on_frame(
                preview, self.capture_zones or [], self.exclusion_zones or []
            )

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
        vid_label = (
            f"  [{video_idx+1}/{len(self.video_paths)}]"
            if len(self.video_paths) > 1 else ""
        )
        cv2.putText(
            preview,
            f"Pedestrians: {grand_total}  |  {speed_x:.1f}x{vid_label}",
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
            f"Pedestrians: {grand_total}"
        )

    # ------------------------------------------------------------------
    # Results compilation
    # ------------------------------------------------------------------

    def _compute_grand_total(self, state: dict) -> int:
        total = 0
        for label in state["per_line_counts"]:
            total += state["per_line_counts"][label]["in"]
            total += state["per_line_counts"][label]["out"]
        return total

    def _emit_results(self, state, video_frame_counts, video_fps_list, process_start):
        total_elapsed = time_mod.time() - process_start

        per_line_results = {}
        grand_total = 0

        for line in self.count_lines:
            label = line["label"]
            count_in = state["per_line_counts"][label]["in"]
            count_out = state["per_line_counts"][label]["out"]
            line_total = count_in + count_out
            grand_total += line_total

            per_line_results[label] = {
                "count_in": count_in,
                "count_out": count_out,
                "total": line_total,
                "intervals": {
                    k: dict(v) for k, v in sorted(
                        state["per_line_intervals"][label].items()
                    )
                },
            }

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
        }

        self.progress.emit(100)
        speed = total_duration / total_elapsed if total_elapsed > 0 else 0
        self.status_update.emit(
            f"Complete — {grand_total} pedestrians counted in "
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
        return (lx2 - lx1) * (py - ly1) - (ly2 - ly1) * (px - lx1)
