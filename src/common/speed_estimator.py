"""Advanced speed estimation from video.

Supports two modes:
1. Calibrated 2D: Traditional pixel displacement / calibration distance
2. Vanishing point: Uses road vanishing point for perspective-corrected speed

The vanishing point method is more accurate for angled cameras but requires
the vanishing point to be set (auto-detected or manually placed).
"""

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SpeedConfig:
    """Speed estimation configuration."""
    enabled: bool = False
    pixels_per_meter: float = 0.0
    point1: tuple = (0, 0)
    point2: tuple = (0, 0)
    real_distance_m: float = 3.5
    # Vanishing point (optional — enables perspective correction)
    vanishing_point: tuple | None = None
    # Filtering
    min_speed_kmh: float = 3.0
    max_speed_kmh: float = 200.0
    smooth_window: int = 20
    min_samples: int = 3


class SpeedEstimator:
    """Estimates vehicle speed from tracked centroid movement."""

    def __init__(self, config: SpeedConfig):
        self.config = config
        self._track_positions: dict[int, list[tuple[float, float, float]]] = defaultdict(list)
        # (x, y, timestamp_sec) history per track

    def update(self, track_id: int, cx: float, cy: float, timestamp_sec: float):
        """Record a new position for a tracked vehicle."""
        self._track_positions[track_id].append((cx, cy, timestamp_sec))
        # Keep only recent positions
        max_history = self.config.smooth_window * 2
        if len(self._track_positions[track_id]) > max_history:
            self._track_positions[track_id] = self._track_positions[track_id][-max_history:]

    def get_speed(self, track_id: int) -> float | None:
        """Get smoothed speed estimate for a track in km/h.

        Returns None if insufficient data.
        """
        positions = self._track_positions.get(track_id, [])
        if len(positions) < self.config.min_samples:
            return None

        recent = positions[-self.config.smooth_window:]
        speeds = []

        for i in range(1, len(recent)):
            x1, y1, t1 = recent[i - 1]
            x2, y2, t2 = recent[i]
            dt = t2 - t1
            if dt <= 0:
                continue

            pixel_dist = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

            if self.config.vanishing_point is not None:
                # Perspective-corrected distance
                meters = self._perspective_distance(x1, y1, x2, y2, pixel_dist)
            else:
                # Standard calibrated distance
                meters = pixel_dist / max(self.config.pixels_per_meter, 0.001)

            speed_kmh = (meters / dt) * 3.6
            if self.config.min_speed_kmh <= speed_kmh <= self.config.max_speed_kmh:
                speeds.append(speed_kmh)

        if not speeds:
            return None

        return round(sum(speeds) / len(speeds), 1)

    def _perspective_distance(
        self, x1: float, y1: float, x2: float, y2: float, pixel_dist: float
    ) -> float:
        """Correct pixel distance for perspective using vanishing point.

        Objects further from camera (closer to vanishing point) appear smaller,
        so the same pixel displacement represents a larger real-world distance.
        """
        vx, vy = self.config.vanishing_point

        # Distance from each point to vanishing point
        d1 = math.sqrt((x1 - vx) ** 2 + (y1 - vy) ** 2)
        d2 = math.sqrt((x2 - vx) ** 2 + (y2 - vy) ** 2)

        # Average distance to VP — closer to VP = further from camera = scale up
        avg_d = (d1 + d2) / 2

        # Reference distance (calibration point average distance to VP)
        ref_d = math.sqrt(
            ((self.config.point1[0] + self.config.point2[0]) / 2 - vx) ** 2
            + ((self.config.point1[1] + self.config.point2[1]) / 2 - vy) ** 2
        )

        if avg_d <= 0 or ref_d <= 0:
            return pixel_dist / max(self.config.pixels_per_meter, 0.001)

        # Scale factor: objects at half the reference distance are twice as far away
        scale = ref_d / avg_d
        corrected_pixels = pixel_dist * scale

        return corrected_pixels / max(self.config.pixels_per_meter, 0.001)

    def cleanup_track(self, track_id: int):
        """Remove tracking data for a completed track."""
        self._track_positions.pop(track_id, None)
