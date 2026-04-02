"""Zone-to-zone Origin-Destination tracking logic.

Tracks vehicles across named polygon zones using cv2.pointPolygonTest().
When a track first enters a zone that becomes its origin; when it later
enters a different zone that becomes its destination.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

from src.common.data_models import NamedZone

logger = logging.getLogger(__name__)


@dataclass
class _TrackState:
    """Internal bookkeeping for a single tracked object."""

    origin_zone: Optional[str] = None
    current_zone: Optional[str] = None
    dest_zone: Optional[str] = None
    austroads_class: str = "1"
    first_timestamp: float = 0.0
    last_timestamp: float = 0.0
    interval_key: str = ""
    zones_visited: list[str] = field(default_factory=list)


@dataclass
class ODPair:
    """A recorded origin-destination pair."""

    track_id: int
    origin_zone: str
    dest_zone: str
    austroads_class: str
    interval_key: str
    timestamp: float


class ZoneTracker:
    """Tracks vehicles across named polygon zones to build O-D pairs.

    Parameters:
        zones: List of NamedZone objects defining the intersection zones.
    """

    def __init__(self, zones: list[NamedZone]) -> None:
        self._zones = list(zones)
        # Pre-compute numpy contours for each zone for fast pointPolygonTest
        self._zone_contours: dict[str, np.ndarray] = {}
        for zone in self._zones:
            if len(zone.polygon) >= 3:
                self._zone_contours[zone.name] = np.array(
                    zone.polygon, dtype=np.int32
                )

        self._tracks: dict[int, _TrackState] = {}
        self._od_pairs: list[ODPair] = []
        self._counts: dict[str, dict[str, int]] = {}  # origin -> dest -> count

    def update(
        self,
        track_id: int,
        cx: int,
        cy: int,
        austroads_class: str,
        interval_key: str,
        timestamp: float,
    ) -> Optional[ODPair]:
        """Per-frame update for a tracked object.

        Args:
            track_id:        Unique tracker ID for the object.
            cx:              Centroid X coordinate (pixels).
            cy:              Centroid Y coordinate (pixels).
            austroads_class: Austroads vehicle classification code.
            interval_key:    Time interval key (e.g. "07:00-07:15").
            timestamp:       Frame timestamp (seconds).

        Returns:
            An ODPair if a complete origin-destination trip was recorded
            on this call, otherwise None.
        """
        # Determine which zone the centroid is in (if any)
        zone_name = self._point_in_zone(cx, cy)

        # Get or create track state
        if track_id not in self._tracks:
            self._tracks[track_id] = _TrackState(
                austroads_class=austroads_class,
                first_timestamp=timestamp,
                last_timestamp=timestamp,
                interval_key=interval_key,
            )

        state = self._tracks[track_id]
        state.last_timestamp = timestamp
        state.austroads_class = austroads_class
        state.interval_key = interval_key

        if zone_name is None:
            # Not in any zone right now
            return None

        # Track entered a zone
        if state.origin_zone is None:
            # First zone entry: this is the origin
            state.origin_zone = zone_name
            state.current_zone = zone_name
            if zone_name not in state.zones_visited:
                state.zones_visited.append(zone_name)
            return None

        if zone_name == state.current_zone:
            # Still in the same zone
            return None

        # Entered a DIFFERENT zone
        state.current_zone = zone_name
        if zone_name not in state.zones_visited:
            state.zones_visited.append(zone_name)

        # If the new zone differs from origin, record O-D pair
        if zone_name != state.origin_zone:
            state.dest_zone = zone_name
            od_pair = ODPair(
                track_id=track_id,
                origin_zone=state.origin_zone,
                dest_zone=zone_name,
                austroads_class=state.austroads_class,
                interval_key=state.interval_key,
                timestamp=state.last_timestamp,
            )
            self._od_pairs.append(od_pair)
            self._increment_count(state.origin_zone, zone_name)
            return od_pair

        return None

    def finalize_track(self, track_id: int) -> Optional[ODPair]:
        """Called when a track is lost or expired.

        If the track visited at least 2 different zones and does not
        already have a recorded O-D pair, record the first and last
        zones as origin and destination.

        Args:
            track_id: The track ID to finalize.

        Returns:
            An ODPair if one was recorded, otherwise None.
        """
        state = self._tracks.pop(track_id, None)
        if state is None:
            return None

        # If already recorded a destination via update(), nothing more to do
        if state.dest_zone is not None:
            return None

        # Check if the track visited at least 2 different zones
        if len(state.zones_visited) >= 2:
            origin = state.zones_visited[0]
            dest = state.zones_visited[-1]
            if origin != dest:
                od_pair = ODPair(
                    track_id=track_id,
                    origin_zone=origin,
                    dest_zone=dest,
                    austroads_class=state.austroads_class,
                    interval_key=state.interval_key,
                    timestamp=state.last_timestamp,
                )
                self._od_pairs.append(od_pair)
                self._increment_count(origin, dest)
                return od_pair

        return None

    def get_od_pairs(self) -> list[ODPair]:
        """Return all recorded O-D pairs."""
        return list(self._od_pairs)

    def get_counts(self) -> dict[str, dict[str, int]]:
        """Return current counts dict: origin -> dest -> count."""
        return {
            origin: dict(dests)
            for origin, dests in self._counts.items()
        }

    def reset(self) -> None:
        """Clear all tracking state."""
        self._tracks.clear()
        self._od_pairs.clear()
        self._counts.clear()

    # ── Internal helpers ──────────────────────────────────────────────

    def _point_in_zone(self, cx: int, cy: int) -> Optional[str]:
        """Return the name of the zone containing (cx, cy), or None."""
        point = (float(cx), float(cy))
        for zone_name, contour in self._zone_contours.items():
            result = cv2.pointPolygonTest(contour, point, False)
            if result >= 0:
                return zone_name
        return None

    def _increment_count(self, origin: str, dest: str) -> None:
        """Increment the O-D count matrix."""
        if origin not in self._counts:
            self._counts[origin] = {}
        self._counts[origin][dest] = self._counts[origin].get(dest, 0) + 1
