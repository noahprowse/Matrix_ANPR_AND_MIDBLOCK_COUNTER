"""Origin-Destination matrix builder.

Accumulates O-D pairs into a nested data structure indexed by time
interval, origin zone, destination zone, and Austroads vehicle class.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


class ODMatrix:
    """Origin-Destination matrix that accumulates counts.

    Internal structure::

        _data[interval_key][origin_zone][dest_zone][class_code] = count
    """

    def __init__(self) -> None:
        # nested defaultdicts: interval -> origin -> dest -> class -> count
        self._data: dict[str, dict[str, dict[str, dict[str, int]]]] = {}

    def add_od_pair(
        self,
        origin: str,
        dest: str,
        class_code: str,
        interval_key: str,
    ) -> None:
        """Increment the count for a single O-D pair.

        Args:
            origin:       Origin zone name.
            dest:         Destination zone name.
            class_code:   Austroads class code (e.g. "1", "3", "CYC").
            interval_key: Time interval key (e.g. "07:00-07:15").
        """
        if interval_key not in self._data:
            self._data[interval_key] = {}
        interval = self._data[interval_key]

        if origin not in interval:
            interval[origin] = {}
        origin_dict = interval[origin]

        if dest not in origin_dict:
            origin_dict[dest] = {}
        dest_dict = origin_dict[dest]

        dest_dict[class_code] = dest_dict.get(class_code, 0) + 1

    def get_total_matrix(self) -> dict[str, dict[str, dict[str, int]]]:
        """Return full O-D matrix summed across all intervals.

        Returns:
            Dict of origin -> dest -> class_code -> count.
        """
        totals: dict[str, dict[str, dict[str, int]]] = {}

        for interval_data in self._data.values():
            for origin, dests in interval_data.items():
                if origin not in totals:
                    totals[origin] = {}
                for dest, classes in dests.items():
                    if dest not in totals[origin]:
                        totals[origin][dest] = {}
                    for cls, count in classes.items():
                        totals[origin][dest][cls] = (
                            totals[origin][dest].get(cls, 0) + count
                        )

        return totals

    def get_matrix_for_interval(
        self, interval_key: str
    ) -> dict[str, dict[str, dict[str, int]]]:
        """Return O-D matrix for a single interval.

        Args:
            interval_key: The time interval to retrieve.

        Returns:
            Dict of origin -> dest -> class_code -> count.
        """
        return dict(self._data.get(interval_key, {}))

    def get_matrix_by_class(
        self, class_code: str
    ) -> dict[str, dict[str, int]]:
        """Return O-D matrix filtered to a single vehicle class.

        Sums across all intervals.

        Args:
            class_code: The Austroads class code to filter on.

        Returns:
            Dict of origin -> dest -> count.
        """
        result: dict[str, dict[str, int]] = {}

        for interval_data in self._data.values():
            for origin, dests in interval_data.items():
                if origin not in result:
                    result[origin] = {}
                for dest, classes in dests.items():
                    count = classes.get(class_code, 0)
                    if count > 0:
                        result[origin][dest] = (
                            result[origin].get(dest, 0) + count
                        )

        return result

    def get_zone_names(self) -> list[str]:
        """Return sorted list of all zone names seen (as origins or dests)."""
        names: set[str] = set()
        for interval_data in self._data.values():
            for origin, dests in interval_data.items():
                names.add(origin)
                names.update(dests.keys())
        return sorted(names)

    def get_interval_keys(self) -> list[str]:
        """Return sorted list of all time interval keys."""
        return sorted(self._data.keys())

    def get_class_codes(self) -> list[str]:
        """Return sorted list of all Austroads class codes seen."""
        codes: set[str] = set()
        for interval_data in self._data.values():
            for dests in interval_data.values():
                for classes in dests.values():
                    codes.update(classes.keys())
        return sorted(codes)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert total O-D matrix to a pandas DataFrame.

        Rows are origin zones, columns are destination zones.
        Values are total counts (all classes summed).

        Returns:
            pandas DataFrame with zone names as index and columns.
        """
        zones = self.get_zone_names()
        summary = self.get_summary()

        data = {}
        for origin in zones:
            row = {}
            for dest in zones:
                row[dest] = summary.get(origin, {}).get(dest, 0)
            data[origin] = row

        df = pd.DataFrame(data).T
        df.index.name = "Origin"
        df.columns.name = "Destination"
        return df

    def get_summary(self) -> dict[str, dict[str, int]]:
        """Return total counts per O-D pair across all classes and intervals.

        Returns:
            Dict of origin -> dest -> total_count.
        """
        result: dict[str, dict[str, int]] = {}
        total_matrix = self.get_total_matrix()

        for origin, dests in total_matrix.items():
            if origin not in result:
                result[origin] = {}
            for dest, classes in dests.items():
                result[origin][dest] = sum(classes.values())

        return result

    def get_total_count(self) -> int:
        """Return the grand total of all O-D pair counts."""
        total = 0
        for interval_data in self._data.values():
            for dests in interval_data.values():
                for classes in dests.values():
                    total += sum(classes.values())
        return total
