"""Turning Movement Count (TMC) derivation from O-D matrix.

Uses Australian LEFT-HAND TRAFFIC rules for turn classification:

    N->S = Through, N->E = Left Turn, N->W = Right Turn, N->N = U-Turn
    S->N = Through, S->W = Left Turn, S->E = Right Turn, S->S = U-Turn
    E->W = Through, E->S = Left Turn, E->N = Right Turn, E->E = U-Turn
    W->E = Through, W->N = Left Turn, W->S = Right Turn, W->W = U-Turn

Supports non-standard intersections (3-leg, 5-leg) with configurable
movement labels.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.intersection.od_matrix import ODMatrix

logger = logging.getLogger(__name__)

# ── Australian left-hand traffic turn classification ──────────────────

# Standard 4-way intersection movements.
# Key: (origin_compass, dest_compass) -> movement type
_LHT_MOVEMENTS: dict[tuple[str, str], str] = {
    # From North
    ("N", "S"): "Through",
    ("N", "E"): "Left",
    ("N", "W"): "Right",
    ("N", "N"): "U-Turn",
    # From South
    ("S", "N"): "Through",
    ("S", "W"): "Left",
    ("S", "E"): "Right",
    ("S", "S"): "U-Turn",
    # From East
    ("E", "W"): "Through",
    ("E", "S"): "Left",
    ("E", "N"): "Right",
    ("E", "E"): "U-Turn",
    # From West
    ("W", "E"): "Through",
    ("W", "N"): "Left",
    ("W", "S"): "Right",
    ("W", "W"): "U-Turn",
    # ── Extended compass directions (for 5+ leg intersections) ──
    ("NE", "SW"): "Through",
    ("NE", "SE"): "Left",
    ("NE", "NW"): "Right",
    ("NE", "NE"): "U-Turn",
    ("NW", "SE"): "Through",
    ("NW", "NE"): "Left",
    ("NW", "SW"): "Right",
    ("NW", "NW"): "U-Turn",
    ("SE", "NW"): "Through",
    ("SE", "SW"): "Left",
    ("SE", "NE"): "Right",
    ("SE", "SE"): "U-Turn",
    ("SW", "NE"): "Through",
    ("SW", "NW"): "Left",
    ("SW", "SE"): "Right",
    ("SW", "SW"): "U-Turn",
}

# Movement type display order
MOVEMENT_ORDER = ["Left", "Through", "Right", "U-Turn"]


class TMCCalculator:
    """Derives Turning Movement Counts from an O-D matrix.

    Parameters:
        approach_config: Dict mapping zone names to compass directions.
                         E.g. {"Zone A": "N", "Zone B": "S", ...}
    """

    def __init__(self, approach_config: dict[str, str]) -> None:
        self._approach_config = dict(approach_config)
        # Reverse mapping: compass direction -> zone name
        self._compass_to_zone: dict[str, str] = {
            v: k for k, v in self._approach_config.items()
        }

    @property
    def approach_config(self) -> dict[str, str]:
        """The zone-to-compass mapping."""
        return dict(self._approach_config)

    def classify_movement(
        self, origin_zone: str, dest_zone: str
    ) -> str:
        """Classify the movement between two zones.

        Args:
            origin_zone: Name of the origin zone.
            dest_zone:   Name of the destination zone.

        Returns:
            Movement type string: "Left", "Through", "Right", "U-Turn",
            or "Unknown" if the zones are not in the approach config.
        """
        origin_compass = self._approach_config.get(origin_zone)
        dest_compass = self._approach_config.get(dest_zone)

        if origin_compass is None or dest_compass is None:
            return "Unknown"

        return _LHT_MOVEMENTS.get(
            (origin_compass, dest_compass), "Unknown"
        )

    def compute_tmc(self, od_matrix: ODMatrix) -> dict:
        """Compute Turning Movement Counts from an O-D matrix.

        Returns:
            TMC data structure::

                tmc[interval_key][approach_zone][movement_type][class_code] = count

            Where approach_zone is the origin zone name, movement_type is
            one of "Left", "Through", "Right", "U-Turn".
        """
        tmc: dict[str, dict[str, dict[str, dict[str, int]]]] = {}

        for interval_key in od_matrix.get_interval_keys():
            interval_matrix = od_matrix.get_matrix_for_interval(interval_key)
            tmc[interval_key] = self._compute_interval_tmc(interval_matrix)

        return tmc

    def get_total_tmc(self, od_matrix: ODMatrix) -> dict:
        """Compute TMC summed across all intervals.

        Returns:
            Dict of approach_zone -> movement_type -> class_code -> count.
        """
        total_matrix = od_matrix.get_total_matrix()
        return self._compute_interval_tmc(total_matrix)

    def get_approach_summary(
        self,
        approach: str,
        tmc_data: dict,
    ) -> dict[str, int]:
        """Get totals for one approach zone across all intervals.

        Args:
            approach:  Zone name of the approach.
            tmc_data:  TMC data structure from compute_tmc().

        Returns:
            Dict of movement_type -> total count.
        """
        totals: dict[str, int] = {m: 0 for m in MOVEMENT_ORDER}

        for interval_movements in tmc_data.values():
            approach_data = interval_movements.get(approach, {})
            for movement, classes in approach_data.items():
                if movement in totals:
                    totals[movement] += sum(classes.values())

        return totals

    def get_movement_totals(
        self, tmc_data: dict
    ) -> dict[str, int]:
        """Get grand total per movement type across all approaches/intervals.

        Args:
            tmc_data: TMC data structure from compute_tmc().

        Returns:
            Dict of movement_type -> total count.
        """
        totals: dict[str, int] = {m: 0 for m in MOVEMENT_ORDER}

        for interval_movements in tmc_data.values():
            for approach_data in interval_movements.values():
                for movement, classes in approach_data.items():
                    if movement in totals:
                        totals[movement] += sum(classes.values())

        return totals

    def get_approach_names(self) -> list[str]:
        """Return zone names sorted by their compass direction."""
        # Sort by a canonical compass order
        order = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        return sorted(
            self._approach_config.keys(),
            key=lambda z: (
                order.index(self._approach_config[z])
                if self._approach_config[z] in order
                else 99
            ),
        )

    # ── Internal helpers ──────────────────────────────────────────────

    def _compute_interval_tmc(
        self,
        interval_matrix: dict[str, dict[str, dict[str, int]]],
    ) -> dict[str, dict[str, dict[str, int]]]:
        """Compute TMC for a single interval's O-D matrix.

        Args:
            interval_matrix: origin -> dest -> class_code -> count.

        Returns:
            approach -> movement -> class_code -> count.
        """
        result: dict[str, dict[str, dict[str, int]]] = {}

        for origin, dests in interval_matrix.items():
            if origin not in self._approach_config:
                continue

            if origin not in result:
                result[origin] = {}

            for dest, classes in dests.items():
                movement = self.classify_movement(origin, dest)
                if movement == "Unknown":
                    continue

                if movement not in result[origin]:
                    result[origin][movement] = {}

                for cls_code, count in classes.items():
                    result[origin][movement][cls_code] = (
                        result[origin][movement].get(cls_code, 0) + count
                    )

        return result
