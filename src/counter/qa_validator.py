"""Quality assurance validator for traffic counting results.

Performs sanity checks on counting data to flag potential issues:
- Excessive zero-count intervals
- Unrealistic heavy vehicle percentages
- Unusual motorcycle percentages
- Active transport on highway-class roads
- Sudden jumps between adjacent intervals
- Missing or incomplete data
"""

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

# Thresholds for QA checks
HEAVY_VEHICLE_PCT_THRESHOLD = 40  # Flag if >40% heavy vehicles (unusual for urban)
MOTORCYCLE_PCT_THRESHOLD = 20     # Flag if >20% motorcycles (unusual outside SE Asia)
ZERO_INTERVAL_WARN_PCT = 30       # Flag if >30% of intervals have zero counts
INTERVAL_JUMP_FACTOR = 5.0        # Flag if adjacent interval count jumps by 5x
MIN_VEHICLES_FOR_CHECKS = 10      # Don't flag percentages if total is very low


class QAFlag:
    """Represents a single QA issue found in the data."""

    SEVERITY_INFO = "info"
    SEVERITY_WARNING = "warning"
    SEVERITY_ERROR = "error"

    def __init__(self, severity: str, category: str, message: str, details: str = ""):
        self.severity = severity
        self.category = category
        self.message = message
        self.details = details

    def __repr__(self):
        return f"QAFlag({self.severity}, {self.category}: {self.message})"

    def to_dict(self) -> dict:
        """Convert to dictionary for reporting."""
        return {
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "details": self.details,
        }


class QAValidator:
    """Validates traffic counting results and flags potential issues."""

    def __init__(self, road_type: str = "urban"):
        """Initialize the validator.

        Args:
            road_type: One of 'urban', 'rural', 'highway', 'residential'.
                       Adjusts thresholds based on expected traffic patterns.
        """
        self.road_type = road_type
        self.flags: list[QAFlag] = []

    def validate(self, results: dict) -> list[QAFlag]:
        """Run all QA checks on counting results.

        Args:
            results: Final results dict from CounterWorker (per_line, grand_total, etc.)

        Returns:
            List of QAFlag objects describing issues found.
        """
        self.flags = []

        if not results or "per_line" not in results:
            self.flags.append(QAFlag(
                QAFlag.SEVERITY_ERROR, "data",
                "No counting results to validate",
            ))
            return self.flags

        for label, line_data in results["per_line"].items():
            self._check_zero_intervals(label, line_data)
            self._check_heavy_vehicle_pct(label, line_data)
            self._check_motorcycle_pct(label, line_data)
            self._check_active_transport(label, line_data)
            self._check_interval_smoothness(label, line_data)
            self._check_directional_balance(label, line_data)

        self._check_total_count(results)

        return self.flags

    def _get_total_vehicles(self, line_data: dict) -> int:
        """Get total vehicle count for a line."""
        return line_data.get("total", 0)

    def _get_class_counts(self, line_data: dict) -> dict[str, int]:
        """Get combined in+out counts by class."""
        counts = defaultdict(int)
        for cls, count in line_data.get("counts_in", {}).items():
            counts[cls] += count
        for cls, count in line_data.get("counts_out", {}).items():
            counts[cls] += count
        return dict(counts)

    def _check_zero_intervals(self, label: str, line_data: dict):
        """Flag if too many intervals have zero vehicles."""
        intervals = line_data.get("intervals", {})
        if not intervals:
            return

        zero_count = 0
        total_intervals = len(intervals)

        for interval_key, class_data in intervals.items():
            interval_total = 0
            for cls, dirs in class_data.items():
                if isinstance(dirs, dict):
                    interval_total += dirs.get("in", 0) + dirs.get("out", 0)
            if interval_total == 0:
                zero_count += 1

        if total_intervals > 0:
            zero_pct = (zero_count / total_intervals) * 100
            if zero_pct > ZERO_INTERVAL_WARN_PCT:
                self.flags.append(QAFlag(
                    QAFlag.SEVERITY_WARNING, "intervals",
                    f"Line '{label}': {zero_pct:.0f}% of intervals have zero counts",
                    f"{zero_count} of {total_intervals} intervals empty. "
                    "Check video quality, counting line placement, or time filter.",
                ))

    def _check_heavy_vehicle_pct(self, label: str, line_data: dict):
        """Flag if heavy vehicle percentage is unusually high."""
        total = self._get_total_vehicles(line_data)
        if total < MIN_VEHICLES_FOR_CHECKS:
            return

        counts = self._get_class_counts(line_data)
        # Heavy vehicles: classes 3-12 (trucks and buses)
        heavy_classes = {"3", "4", "5", "6", "7", "8", "9", "10", "11", "12"}
        heavy_count = sum(counts.get(c, 0) for c in heavy_classes)
        heavy_pct = (heavy_count / total) * 100

        if heavy_pct > HEAVY_VEHICLE_PCT_THRESHOLD:
            self.flags.append(QAFlag(
                QAFlag.SEVERITY_WARNING, "classification",
                f"Line '{label}': {heavy_pct:.1f}% heavy vehicles (>{HEAVY_VEHICLE_PCT_THRESHOLD}%)",
                "Unusual for most urban roads. Check if camera angle is causing "
                "misclassification of cars as trucks, or if this is an industrial area.",
            ))

    def _check_motorcycle_pct(self, label: str, line_data: dict):
        """Flag if motorcycle percentage is unusually high."""
        total = self._get_total_vehicles(line_data)
        if total < MIN_VEHICLES_FOR_CHECKS:
            return

        counts = self._get_class_counts(line_data)
        moto_count = counts.get("1M", 0)
        moto_pct = (moto_count / total) * 100

        if moto_pct > MOTORCYCLE_PCT_THRESHOLD:
            self.flags.append(QAFlag(
                QAFlag.SEVERITY_INFO, "classification",
                f"Line '{label}': {moto_pct:.1f}% motorcycles (>{MOTORCYCLE_PCT_THRESHOLD}%)",
                "Higher than typical for Australian/Western roads. Verify if bicycles "
                "or e-scooters are being classified as motorcycles.",
            ))

    def _check_active_transport(self, label: str, line_data: dict):
        """Flag if active transport is detected on a highway."""
        if self.road_type != "highway":
            return

        counts = self._get_class_counts(line_data)
        at_count = counts.get("AT", 0)

        if at_count > 0:
            self.flags.append(QAFlag(
                QAFlag.SEVERITY_WARNING, "classification",
                f"Line '{label}': {at_count} active transport detections on highway",
                "Pedestrians/cyclists on a highway is unusual. May be false detections "
                "from roadside objects, or road type may need to be changed.",
            ))

    def _check_interval_smoothness(self, label: str, line_data: dict):
        """Flag sudden jumps between adjacent intervals."""
        intervals = line_data.get("intervals", {})
        if len(intervals) < 3:
            return

        sorted_keys = sorted(intervals.keys())
        interval_totals = []

        for key in sorted_keys:
            class_data = intervals[key]
            total = 0
            for cls, dirs in class_data.items():
                if isinstance(dirs, dict):
                    total += dirs.get("in", 0) + dirs.get("out", 0)
            interval_totals.append((key, total))

        jump_count = 0
        for i in range(1, len(interval_totals)):
            prev_key, prev_total = interval_totals[i - 1]
            curr_key, curr_total = interval_totals[i]

            # Only flag if both intervals have meaningful counts
            if prev_total >= 3 and curr_total >= 3:
                ratio = max(curr_total, prev_total) / min(curr_total, prev_total)
                if ratio >= INTERVAL_JUMP_FACTOR:
                    jump_count += 1

        if jump_count > 0:
            self.flags.append(QAFlag(
                QAFlag.SEVERITY_INFO, "intervals",
                f"Line '{label}': {jump_count} sudden jumps between adjacent intervals",
                f"Adjacent intervals differ by {INTERVAL_JUMP_FACTOR}x or more. "
                "May indicate video gaps, occlusion, or counting line issues.",
            ))

    def _check_directional_balance(self, label: str, line_data: dict):
        """Flag severely unbalanced directional counts."""
        total_in = line_data.get("total_in", 0)
        total_out = line_data.get("total_out", 0)
        total = total_in + total_out

        if total < MIN_VEHICLES_FOR_CHECKS:
            return

        if total_in == 0 or total_out == 0:
            self.flags.append(QAFlag(
                QAFlag.SEVERITY_INFO, "direction",
                f"Line '{label}': all vehicles counted in one direction only",
                f"In: {total_in}, Out: {total_out}. "
                "This is normal for one-way roads but may indicate a "
                "counting line orientation issue on two-way roads.",
            ))

    def _check_total_count(self, results: dict):
        """Flag if grand total seems too low for the duration."""
        grand_total = results.get("grand_total", 0)
        duration_sec = results.get("duration_sec", 0)
        duration_hours = duration_sec / 3600 if duration_sec > 0 else 0

        if duration_hours >= 1 and grand_total < 5:
            self.flags.append(QAFlag(
                QAFlag.SEVERITY_WARNING, "data",
                f"Only {grand_total} vehicles in {duration_hours:.1f} hours",
                "Very low count. Check video quality, model confidence, "
                "counting line placement, and time filter settings.",
            ))

    def get_summary(self) -> dict:
        """Get a summary of all QA flags."""
        return {
            "total_flags": len(self.flags),
            "errors": sum(1 for f in self.flags if f.severity == QAFlag.SEVERITY_ERROR),
            "warnings": sum(1 for f in self.flags if f.severity == QAFlag.SEVERITY_WARNING),
            "info": sum(1 for f in self.flags if f.severity == QAFlag.SEVERITY_INFO),
            "flags": [f.to_dict() for f in self.flags],
        }
