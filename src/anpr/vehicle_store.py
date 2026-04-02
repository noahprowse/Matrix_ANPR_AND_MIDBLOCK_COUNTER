"""In-memory vehicle database for ANPR processing.

Accumulates vehicle detection results from multiple worker streams,
groups readings by track ID (intra-video) and plate text (cross-video),
and provides the data for the QA review page.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict

from src.common.data_models import VehicleReading, VehicleRecord

logger = logging.getLogger(__name__)


class VehicleStore:
    """Thread-safe accumulator for vehicle detections during processing.

    Results arrive from MonitorBridge (main thread) so technically single-
    threaded, but we guard with a lock for safety.

    Supports cross-chunk deduplication: when a video is split into
    overlapping chunks, the same vehicle may be detected by two workers.
    Overlap-zone detections are matched against existing records by
    plate text + time proximity and merged rather than double-counted.
    """

    # Maximum time difference (seconds) between two readings to consider
    # them the same vehicle during overlap dedup.
    _DEDUP_TIME_TOLERANCE = 10

    def __init__(self):
        self._lock = threading.Lock()
        self._vehicles: dict[str, VehicleRecord] = {}  # vehicle_id -> record
        self._next_id = 1

        # Lookup: (video_file, track_id) -> vehicle_id
        self._track_index: dict[tuple[str, int], str] = {}

        # Reverse lookup for dedup: (video_file, plate_text) -> vehicle_id
        # Used to merge overlap-zone detections across chunk boundaries.
        self._plate_index: dict[tuple[str, str], str] = {}

    # ── Public API ──────────────────────────────────────────────────

    def add_detection(self, result: dict) -> VehicleRecord:
        """Add a detection result from a worker subprocess.

        If a vehicle with the same (video_file, track_id) already exists,
        the reading is appended. Otherwise a new VehicleRecord is created.

        When ``is_overlap`` is True in the result, the detection came from
        a chunk's overlap zone and we attempt to match it to an existing
        vehicle by plate text + time proximity before creating a new one.

        Args:
            result: Dict from IPC with keys: track_id, plate_text, confidence,
                    is_valid, direction, real_time, video_file, frame_num,
                    vehicle_crop_path, plate_crop_path, source, is_overlap.

        Returns:
            The VehicleRecord that was created or updated.
        """
        with self._lock:
            video_file = result.get("video_file", "")
            track_id = result.get("track_id", 0)
            is_overlap = result.get("is_overlap", False)
            plate_text = result.get("plate_text", "")
            real_time = result.get("real_time", "")
            key = (video_file, track_id)

            reading = VehicleReading(
                plate_text=plate_text,
                confidence=result.get("confidence", 0.0),
                is_valid_format=result.get("is_valid", False),
                frame_num=result.get("frame_num", 0),
                real_time=real_time,
                video_file=video_file,
                plate_crop_path=result.get("plate_crop_path", ""),
                source=result.get("source", "paddle"),
            )

            # ── Check for existing track match ──
            if key in self._track_index:
                vehicle_id = self._track_index[key]
                vehicle = self._vehicles[vehicle_id]
                return self._merge_reading(vehicle, reading, result)

            # ── Overlap dedup: match by plate text + time ──
            if is_overlap and plate_text:
                dedup_id = self._find_overlap_match(
                    video_file, plate_text, real_time,
                )
                if dedup_id:
                    # This overlap detection matches an existing vehicle
                    # from the previous chunk — merge it.
                    self._track_index[key] = dedup_id
                    vehicle = self._vehicles[dedup_id]
                    return self._merge_reading(vehicle, reading, result)

            # ── New vehicle ──
            vehicle_id = f"v{self._next_id:04d}"
            self._next_id += 1
            self._track_index[key] = vehicle_id

            confidence = result.get("confidence", 0.0)
            vehicle = VehicleRecord(
                vehicle_id=vehicle_id,
                track_id=track_id,
                video_file=video_file,
                direction=result.get("direction", ""),
                vehicle_crop_path=result.get("vehicle_crop_path", ""),
                readings=[reading],
                best_reading_idx=0,
                flagged_for_review=confidence < 70.0,
            )
            self._vehicles[vehicle_id] = vehicle

            # Update plate index for future dedup lookups
            if plate_text:
                self._plate_index[(video_file, plate_text)] = vehicle_id

            return vehicle

    def _merge_reading(
        self,
        vehicle: VehicleRecord,
        reading: VehicleReading,
        result: dict,
    ) -> VehicleRecord:
        """Merge a new reading into an existing vehicle record."""
        vehicle.readings.append(reading)

        # Update best reading if this one has higher confidence
        if reading.confidence > vehicle.best_reading.confidence:
            vehicle.best_reading_idx = len(vehicle.readings) - 1
            crop_path = result.get("vehicle_crop_path", "")
            if crop_path:
                vehicle.vehicle_crop_path = crop_path

        # Update direction if not yet set
        direction = result.get("direction", "")
        if direction and not vehicle.direction:
            vehicle.direction = direction

        # Re-evaluate flagged status
        vehicle.flagged_for_review = vehicle.best_reading.confidence < 70.0

        # Update plate index
        plate_text = reading.plate_text
        if plate_text:
            self._plate_index[
                (vehicle.video_file, plate_text)
            ] = vehicle.vehicle_id

        return vehicle

    def _find_overlap_match(
        self,
        video_file: str,
        plate_text: str,
        real_time: str,
    ) -> str | None:
        """Find an existing vehicle that matches this overlap-zone detection.

        Returns the vehicle_id if a match is found, None otherwise.
        """
        candidate_id = self._plate_index.get((video_file, plate_text))
        if not candidate_id:
            return None

        candidate = self._vehicles.get(candidate_id)
        if not candidate:
            return None

        # Check time proximity
        if real_time and candidate.best_reading.real_time:
            delta = abs(
                self._time_to_seconds(real_time)
                - self._time_to_seconds(candidate.best_reading.real_time)
            )
            if delta <= self._DEDUP_TIME_TOLERANCE:
                return candidate_id

        # If no time info, match on plate text alone (weaker but acceptable)
        if not real_time or not candidate.best_reading.real_time:
            return candidate_id

        return None

    @staticmethod
    def _time_to_seconds(time_str: str) -> int:
        """Convert HH:MM:SS to total seconds for comparison."""
        try:
            parts = time_str.split(":")
            h = int(parts[0]) if len(parts) > 0 else 0
            m = int(parts[1]) if len(parts) > 1 else 0
            s = int(parts[2]) if len(parts) > 2 else 0
            return h * 3600 + m * 60 + s
        except (ValueError, IndexError):
            return 0

    def get_all_vehicles(self) -> list[VehicleRecord]:
        """Return all vehicles sorted by first detection time."""
        with self._lock:
            vehicles = list(self._vehicles.values())
        # Sort by first reading's real_time, then by vehicle_id
        vehicles.sort(key=lambda v: (v.readings[0].real_time if v.readings else "", v.vehicle_id))
        return vehicles

    def get_flagged(self) -> list[VehicleRecord]:
        """Return only vehicles flagged for review (confidence < 70%)."""
        return [v for v in self.get_all_vehicles() if v.flagged_for_review]

    def get_vehicle(self, vehicle_id: str) -> VehicleRecord | None:
        """Get a specific vehicle by ID."""
        with self._lock:
            return self._vehicles.get(vehicle_id)

    def group_by_plate(self) -> dict[str, list[VehicleRecord]]:
        """Group vehicles by their current plate text.

        Vehicles with the same plate text (across different videos or
        track IDs) are grouped together — likely the same physical vehicle.
        """
        groups: dict[str, list[VehicleRecord]] = defaultdict(list)
        for vehicle in self.get_all_vehicles():
            plate = vehicle.plate_text
            if plate:
                groups[plate].append(vehicle)
            else:
                groups["(no reading)"].append(vehicle)
        return dict(groups)

    def apply_correction(self, vehicle_id: str, new_plate: str) -> bool:
        """Apply a user correction to a vehicle's plate text.

        Returns True if the vehicle was found and updated.
        """
        with self._lock:
            vehicle = self._vehicles.get(vehicle_id)
            if vehicle is None:
                return False
            vehicle.user_corrected_plate = new_plate
            vehicle.flagged_for_review = False
            return True

    def apply_ai_result(self, vehicle_id: str, plate_text: str, confidence: float) -> bool:
        """Apply an AI validation result as a new reading.

        Returns True if the vehicle was found and updated.
        """
        with self._lock:
            vehicle = self._vehicles.get(vehicle_id)
            if vehicle is None:
                return False

            reading = VehicleReading(
                plate_text=plate_text,
                confidence=confidence,
                is_valid_format=True,
                frame_num=vehicle.best_reading.frame_num,
                real_time=vehicle.best_reading.real_time,
                video_file=vehicle.best_reading.video_file,
                plate_crop_path=vehicle.best_reading.plate_crop_path,
                source="claude",
            )
            vehicle.readings.append(reading)

            # If AI reading is higher confidence, update best
            if confidence > vehicle.best_reading.confidence:
                vehicle.best_reading_idx = len(vehicle.readings) - 1

            vehicle.flagged_for_review = False
            return True

    def to_export_list(self) -> list[dict]:
        """Return a flat list of dicts for Excel export.

        Each vehicle produces one row with the best/corrected plate text.
        """
        rows = []
        for vehicle in self.get_all_vehicles():
            best = vehicle.best_reading
            rows.append({
                "vehicle_id": vehicle.vehicle_id,
                "plate": vehicle.plate_text,
                "confidence": best.confidence,
                "real_time": best.real_time,
                "direction": vehicle.direction,
                "video_file": best.video_file,
                "is_valid": best.is_valid_format,
                "readings_count": len(vehicle.readings),
                "user_corrected": vehicle.user_corrected_plate or "",
                "vehicle_crop_path": vehicle.vehicle_crop_path,
                "plate_crop_path": best.plate_crop_path,
            })
        return rows

    @property
    def total_vehicles(self) -> int:
        with self._lock:
            return len(self._vehicles)

    @property
    def total_flagged(self) -> int:
        with self._lock:
            return sum(1 for v in self._vehicles.values() if v.flagged_for_review)

    @property
    def total_corrected(self) -> int:
        with self._lock:
            return sum(1 for v in self._vehicles.values() if v.user_corrected_plate)
