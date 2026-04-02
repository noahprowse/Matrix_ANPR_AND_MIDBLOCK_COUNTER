"""Job folder browser widget for Matrix Traffic video discovery.

Scans a job folder structure to discover sites, dates, and video files:

    AUQLD-12345/                (job folder - job number)
      3 WB/                     (site folder - site number + direction)
      OD 3 WB/                  (alternative site folder format)
        2025_11_29/             (date folder - YYYY_MM_DD)
          *.avi, *.mp4, ...     (video files)
"""

import logging
import os
import re
from pathlib import Path

from PySide6.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QTreeWidget,
    QTreeWidgetItem,
    QDateEdit,
    QTimeEdit,
    QCheckBox,
)
from PySide6.QtCore import Qt, Signal, QDate, QTime

from src.common.theme import TEXT_MUTED, TEXT_SECONDARY, SUCCESS

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".ts"}

# Matches date folders like 2025_11_29
_DATE_FOLDER_RE = re.compile(r"^\d{4}_\d{2}_\d{2}$")

# Matches site folders: optional "OD " prefix, then a number, then a direction
# e.g. "3 WB", "OD 3 WB", "12 NB", "OD 12 NB"
_SITE_FOLDER_RE = re.compile(r"^(?:OD\s+)?(\d+)\s+(.+)$")


def _find_videos(folder: str) -> list[str]:
    """Return sorted list of video file paths in *folder* (non-recursive)."""
    videos = []
    try:
        for entry in os.scandir(folder):
            if entry.is_file() and Path(entry.name).suffix.lower() in VIDEO_EXTENSIONS:
                videos.append(entry.path)
    except OSError as e:
        logger.warning("Cannot read folder %s: %s", folder, e)
    videos.sort(key=lambda p: os.path.basename(p).lower())
    return videos


class JobFolderWidget(QGroupBox):
    """Widget for browsing a Matrix Traffic job folder structure.

    Discovers video files organised by site and date, and lets the user
    select which sites/dates to process.

    Signals
    -------
    job_loaded : dict
        Emitted after a successful scan.  Payload::

            {
                "job_number": str,
                "sites": [
                    {
                        "site_id": str,
                        "site_name": str,
                        "date": str,          # YYYY_MM_DD
                        "video_paths": [str],
                    },
                    ...
                ],
            }

    videos_selected : list[str]
        Flat list of video paths currently selected for processing.
    """

    job_loaded = Signal(dict)
    videos_selected = Signal(list)

    def __init__(self, parent=None):
        super().__init__("Job Folder", parent)
        self._job_number: str = ""
        self._job_name: str = ""
        self._root_path: str = ""
        self._scan_result: dict | None = None
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Browse row
        browse_row = QHBoxLayout()
        browse_row.setSpacing(8)

        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Select a job folder...")
        self._path_edit.setReadOnly(True)
        browse_row.addWidget(self._path_edit, 1)

        self._browse_btn = QPushButton("Browse Job Folder")
        self._browse_btn.setObjectName("primary_btn")
        self._browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._browse_btn.clicked.connect(self._on_browse)
        browse_row.addWidget(self._browse_btn)

        layout.addLayout(browse_row)

        # Job number display
        job_row = QHBoxLayout()
        job_row.setSpacing(8)

        lbl = QLabel("Job Number:")
        lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        job_row.addWidget(lbl)

        self._job_number_label = QLabel("—")
        self._job_number_label.setStyleSheet(f"color: {SUCCESS}; font-size: 13px; font-weight: bold;")
        job_row.addWidget(self._job_number_label)
        job_row.addStretch()

        layout.addLayout(job_row)

        # Date filter row
        date_filter_row = QHBoxLayout()
        date_filter_row.setSpacing(8)

        self._date_filter_cb = QCheckBox("Filter by survey dates")
        self._date_filter_cb.setChecked(False)
        self._date_filter_cb.toggled.connect(self._on_date_filter_toggled)
        date_filter_row.addWidget(self._date_filter_cb)

        start_date_col = QVBoxLayout()
        lbl = QLabel("Start Date:")
        lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        self._start_date = QDateEdit()
        self._start_date.setDisplayFormat("yyyy-MM-dd")
        self._start_date.setCalendarPopup(True)
        self._start_date.setDate(QDate.currentDate())
        self._start_date.setEnabled(False)
        self._start_date.dateChanged.connect(self._on_filter_changed)
        start_date_col.addWidget(lbl)
        start_date_col.addWidget(self._start_date)
        date_filter_row.addLayout(start_date_col)

        end_date_col = QVBoxLayout()
        lbl = QLabel("End Date:")
        lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        self._end_date = QDateEdit()
        self._end_date.setDisplayFormat("yyyy-MM-dd")
        self._end_date.setCalendarPopup(True)
        self._end_date.setDate(QDate.currentDate())
        self._end_date.setEnabled(False)
        self._end_date.dateChanged.connect(self._on_filter_changed)
        end_date_col.addWidget(lbl)
        end_date_col.addWidget(self._end_date)
        date_filter_row.addLayout(end_date_col)

        layout.addLayout(date_filter_row)

        # Time filter row
        time_filter_row = QHBoxLayout()
        time_filter_row.setSpacing(8)

        self._time_filter_cb = QCheckBox("Filter by time window")
        self._time_filter_cb.setChecked(False)
        self._time_filter_cb.toggled.connect(self._on_time_filter_toggled)
        time_filter_row.addWidget(self._time_filter_cb)

        start_time_col = QVBoxLayout()
        lbl = QLabel("Start Time:")
        lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        self._start_time = QTimeEdit()
        self._start_time.setDisplayFormat("HH:mm")
        self._start_time.setTime(QTime(7, 0))
        self._start_time.setEnabled(False)
        self._start_time.timeChanged.connect(self._on_filter_changed)
        start_time_col.addWidget(lbl)
        start_time_col.addWidget(self._start_time)
        time_filter_row.addLayout(start_time_col)

        end_time_col = QVBoxLayout()
        lbl = QLabel("End Time:")
        lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        self._end_time = QTimeEdit()
        self._end_time.setDisplayFormat("HH:mm")
        self._end_time.setTime(QTime(19, 0))
        self._end_time.setEnabled(False)
        self._end_time.timeChanged.connect(self._on_filter_changed)
        end_time_col.addWidget(lbl)
        end_time_col.addWidget(self._end_time)
        time_filter_row.addLayout(end_time_col)

        layout.addLayout(time_filter_row)

        # Tree view for discovered sites / dates / video counts
        tree_label = QLabel("Discovered Sites & Dates:")
        tree_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        layout.addWidget(tree_label)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Name", "Videos"])
        self._tree.setColumnWidth(0, 280)
        self._tree.setMinimumHeight(160)
        self._tree.setMaximumHeight(300)
        self._tree.setRootIsDecorated(True)
        self._tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._tree)

        # Bottom row: info + confirm
        bottom_row = QHBoxLayout()

        self._info_label = QLabel("No job folder selected")
        self._info_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self._info_label.setWordWrap(True)
        bottom_row.addWidget(self._info_label, 1)

        self._confirm_btn = QPushButton("Load Selected Videos")
        self._confirm_btn.setObjectName("primary_btn")
        self._confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._confirm_btn.setEnabled(False)
        self._confirm_btn.clicked.connect(self._on_confirm)
        bottom_row.addWidget(self._confirm_btn)

        layout.addLayout(bottom_row)

    # ------------------------------------------------------------------
    # Filter toggle handlers
    # ------------------------------------------------------------------

    def _on_date_filter_toggled(self, enabled: bool):
        self._start_date.setEnabled(enabled)
        self._end_date.setEnabled(enabled)
        self._on_filter_changed()

    def _on_time_filter_toggled(self, enabled: bool):
        self._start_time.setEnabled(enabled)
        self._end_time.setEnabled(enabled)
        self._on_filter_changed()

    def _on_filter_changed(self):
        """Re-apply filters when date/time filter settings change."""
        if self._scan_result:
            self._populate_tree(self._scan_result)

    # ------------------------------------------------------------------
    # Browse and scan
    # ------------------------------------------------------------------

    def _on_browse(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select Job Folder", "", QFileDialog.Option.ShowDirsOnly
        )
        if not path:
            return

        self._root_path = path
        self._path_edit.setText(path)

        result = self.scan_folder(path)
        self._scan_result = result

        self._job_number = result.get("job_number", "")
        self._job_name = result.get("job_name", "")
        display = self._job_number
        if self._job_name:
            display += f" — {self._job_name}"
        if display:
            self._job_number_label.setText(display)
        else:
            self._job_number_label.setText("(not detected)")

        # Auto-populate date range from discovered dates
        self._auto_set_date_range(result)

        self._populate_tree(result)
        self.job_loaded.emit(result)

    def scan_folder(self, root_path: str) -> dict:
        """Scan a job folder and return discovered structure.

        Parameters
        ----------
        root_path : str
            Path to the top-level job folder (e.g. ``C:/jobs/AUQLD-12345``).

        Returns
        -------
        dict
            ``{"job_number": str, "job_name": str, "sites": [...], "all_dates": [...]}``
        """
        root = Path(root_path)
        folder_name = root.name  # e.g. "AUQLD-12345 - Project Name"

        # Split folder name on hyphen/dash to extract job_number and job_name
        # Patterns: "12345 - Name", "AUQLD-12345 - Name", "12345"
        if " - " in folder_name:
            parts = folder_name.split(" - ", 1)
            job_number = parts[0].strip()
            job_name = parts[1].strip() if len(parts) > 1 else ""
        elif "-" in folder_name:
            # Could be "AUQLD-12345" (single token) or "12345-Name"
            parts = folder_name.split("-", 1)
            job_number = folder_name  # keep full name as job number
            job_name = ""
        else:
            job_number = folder_name
            job_name = ""

        sites: list[dict] = []

        try:
            subdirs = sorted(
                [d for d in root.iterdir() if d.is_dir()],
                key=lambda d: d.name.lower(),
            )
        except OSError as e:
            logger.error("Cannot read job folder %s: %s", root_path, e)
            return {"job_number": job_number, "sites": []}

        for site_dir in subdirs:
            site_match = _SITE_FOLDER_RE.match(site_dir.name)
            if site_match:
                site_id = site_match.group(1)
                site_name = site_dir.name  # keep full name like "OD 3 WB"
                direction = site_match.group(2).strip()  # e.g. "WB", "NB"
            else:
                # Treat any subfolder as a potential site even if naming
                # doesn't match the expected pattern
                site_id = site_dir.name
                site_name = site_dir.name
                direction = ""

            # Look for date sub-folders
            try:
                date_dirs = sorted(
                    [d for d in site_dir.iterdir() if d.is_dir() and _DATE_FOLDER_RE.match(d.name)],
                    key=lambda d: d.name,
                )
            except OSError:
                date_dirs = []

            if date_dirs:
                for date_dir in date_dirs:
                    videos = _find_videos(str(date_dir))
                    if videos:
                        sites.append({
                            "site_id": site_id,
                            "site_name": site_name,
                            "direction": direction,
                            "date": date_dir.name,
                            "video_paths": videos,
                        })
            else:
                # No date sub-folders — check for videos directly in the site folder
                videos = _find_videos(str(site_dir))
                if videos:
                    sites.append({
                        "site_id": site_id,
                        "site_name": site_name,
                        "direction": direction,
                        "date": "",
                        "video_paths": videos,
                    })

        # Collect all unique dates
        all_dates = sorted({s["date"] for s in sites if s.get("date") and _DATE_FOLDER_RE.match(s["date"])})

        return {
            "job_number": job_number,
            "job_name": job_name,
            "sites": sites,
            "all_dates": all_dates,
        }

    # ------------------------------------------------------------------
    # Tree population
    # ------------------------------------------------------------------

    def _auto_set_date_range(self, result: dict):
        """Set the date filter range from the earliest/latest discovered dates."""
        dates: list[str] = []
        for site in result.get("sites", []):
            d = site.get("date", "")
            if d and _DATE_FOLDER_RE.match(d):
                dates.append(d)
        if not dates:
            return

        dates.sort()
        earliest = dates[0]
        latest = dates[-1]

        def _to_qdate(date_str: str) -> QDate:
            parts = date_str.split("_")
            return QDate(int(parts[0]), int(parts[1]), int(parts[2]))

        self._start_date.setDate(_to_qdate(earliest))
        self._end_date.setDate(_to_qdate(latest))

    def _populate_tree(self, result: dict):
        """Fill the tree widget from scan results, applying current filters."""
        self._tree.blockSignals(True)
        self._tree.clear()

        sites = result.get("sites", [])

        # Apply date filter
        if self._date_filter_cb.isChecked():
            start_d = self._start_date.date()
            end_d = self._end_date.date()
            filtered = []
            for site in sites:
                d = site.get("date", "")
                if d and _DATE_FOLDER_RE.match(d):
                    parts = d.split("_")
                    qd = QDate(int(parts[0]), int(parts[1]), int(parts[2]))
                    if qd < start_d or qd > end_d:
                        continue
                filtered.append(site)
            sites = filtered

        # Apply time filter (match against video filenames like 070000_080000.avi)
        if self._time_filter_cb.isChecked():
            start_t = self._start_time.time()
            end_t = self._end_time.time()
            filtered_sites = []
            for site in sites:
                filtered_videos = []
                for vp in site["video_paths"]:
                    fname = os.path.basename(vp)
                    name_no_ext = os.path.splitext(fname)[0]
                    # Try to extract start time from filename pattern HHMMSS_HHMMSS
                    time_match = re.match(r"^(\d{6})(?:_\d{6})?", name_no_ext)
                    if time_match:
                        t_str = time_match.group(1)
                        file_time = QTime(int(t_str[0:2]), int(t_str[2:4]), int(t_str[4:6]))
                        if file_time < start_t or file_time > end_t:
                            continue
                    filtered_videos.append(vp)
                if filtered_videos:
                    filtered_sites.append({**site, "video_paths": filtered_videos})
            sites = filtered_sites

        # Group by site_name for the tree
        # site_name -> { date -> [video_paths] }
        grouped: dict[str, dict[str, list[str]]] = {}
        for site in sites:
            sname = site["site_name"]
            date_str = site.get("date", "(no date)")
            grouped.setdefault(sname, {}).setdefault(date_str, []).extend(site["video_paths"])

        total_videos = 0
        for site_name in sorted(grouped.keys(), key=str.lower):
            dates_map = grouped[site_name]
            site_video_count = sum(len(v) for v in dates_map.values())
            total_videos += site_video_count

            site_item = QTreeWidgetItem(self._tree)
            site_item.setText(0, site_name)
            site_item.setText(1, str(site_video_count))
            site_item.setFlags(site_item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
            site_item.setCheckState(0, Qt.CheckState.Checked)

            for date_str in sorted(dates_map.keys()):
                vids = dates_map[date_str]
                date_item = QTreeWidgetItem(site_item)
                display_date = date_str.replace("_", "-") if date_str != "(no date)" else date_str
                date_item.setText(0, display_date)
                date_item.setText(1, str(len(vids)))
                date_item.setFlags(date_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                date_item.setCheckState(0, Qt.CheckState.Checked)
                # Store video paths on the date item for retrieval
                date_item.setData(0, Qt.ItemDataRole.UserRole, vids)

        self._tree.expandAll()
        self._tree.blockSignals(False)

        self._update_info(total_videos, len(grouped))
        self._confirm_btn.setEnabled(total_videos > 0)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        """Update info label and propagate check state when user toggles items."""
        self._update_selection_info()

    def _update_selection_info(self):
        selected = self.get_selected_videos()
        count = len(selected)
        if count == 0:
            self._info_label.setText("No videos selected")
            self._info_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
            self._confirm_btn.setEnabled(False)
        else:
            self._info_label.setText(f"{count} video{'s' if count != 1 else ''} selected for processing")
            self._info_label.setStyleSheet(f"color: {SUCCESS}; font-size: 11px;")
            self._confirm_btn.setEnabled(True)

    def _update_info(self, total_videos: int, site_count: int):
        if total_videos == 0:
            self._info_label.setText("No videos found in job folder")
            self._info_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        else:
            self._info_label.setText(
                f"{site_count} site{'s' if site_count != 1 else ''}  |  "
                f"{total_videos} video{'s' if total_videos != 1 else ''} discovered"
            )
            self._info_label.setStyleSheet(f"color: {SUCCESS}; font-size: 11px;")

    # ------------------------------------------------------------------
    # Selection and confirmation
    # ------------------------------------------------------------------

    def _on_confirm(self):
        """Emit the videos_selected signal with the currently checked videos."""
        selected = self.get_selected_videos()
        if selected:
            self.videos_selected.emit(selected)

    def get_selected_videos(self) -> list[str]:
        """Return a flat, sorted list of video paths that are currently checked."""
        videos: list[str] = []
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            site_item = root.child(i)
            for j in range(site_item.childCount()):
                date_item = site_item.child(j)
                if date_item.checkState(0) != Qt.CheckState.Unchecked:
                    paths = date_item.data(0, Qt.ItemDataRole.UserRole)
                    if paths:
                        videos.extend(paths)
        videos.sort(key=lambda p: os.path.basename(p).lower())
        return videos

    def get_job_info(self) -> dict:
        """Return parsed job information for auto-populating survey fields.

        Returns
        -------
        dict
            Full scan result enriched with ``job_name``, ``sites`` with
            directions, ``all_dates``, and ``job_folder_path``.
        """
        result = dict(self._scan_result) if self._scan_result else {}
        result["job_folder_path"] = self._root_path

        # Add list of unique site summaries (site_id, site_name, direction)
        sites_summary = []
        seen = set()
        for site in result.get("sites", []):
            key = site["site_name"]
            if key not in seen:
                seen.add(key)
                match = _SITE_FOLDER_RE.match(key)
                sites_summary.append({
                    "site_id": match.group(1) if match else key,
                    "site_name": key,
                    "direction": site.get("direction", ""),
                })
        result["sites_summary"] = sites_summary

        return result
