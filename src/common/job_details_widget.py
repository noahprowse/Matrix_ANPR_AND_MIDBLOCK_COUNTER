"""Expanded job details input form — Step 2 of the 3-step wizard.

Collects: job number, job name, survey dates/times, classification preset,
and site details.  Emits a fully-populated ``JobConfig`` when the user
clicks Continue.

Can be pre-populated from a folder scan via ``set_from_scan()``.
The ``show_classification`` flag hides the classification section (e.g. for ANPR).
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, QTime, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from src.common.classification_widget import ClassificationWidget
from src.common.data_models import ClassificationConfig, JobConfig, SiteConfig
from src.common.theme import (
    ACCENT,
    ACCENT_LIGHT,
    BG_PRIMARY,
    BG_SECONDARY,
    BORDER,
    DANGER,
    SECTION_HEADER,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class _SiteEntry(QWidget):
    """A single site row with name and direction inputs."""

    removed = Signal(object)

    def __init__(self, index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.index = index
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._number_label = QLabel(f"Site {index + 1}:")
        self._number_label.setFixedWidth(60)
        self._number_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-weight: 600;")
        layout.addWidget(self._number_label)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Site name (e.g. OD 3 WB)")
        layout.addWidget(self._name_edit, 2)

        self._direction_combo = QComboBox()
        self._direction_combo.addItems(["", "NB", "SB", "EB", "WB", "NE", "NW", "SE", "SW"])
        self._direction_combo.setFixedWidth(80)
        layout.addWidget(self._direction_combo)

        self._remove_btn = QPushButton("x")
        self._remove_btn.setFixedSize(28, 28)
        self._remove_btn.setStyleSheet(
            f"QPushButton {{ color: {TEXT_MUTED}; border: 1px solid {BORDER}; "
            f"border-radius: 4px; font-size: 12px; padding: 0; }}"
            f"QPushButton:hover {{ color: {DANGER}; border-color: {DANGER}; }}"
        )
        self._remove_btn.clicked.connect(lambda: self.removed.emit(self))
        layout.addWidget(self._remove_btn)

    def update_index(self, index: int) -> None:
        self.index = index
        self._number_label.setText(f"Site {index + 1}:")

    def get_site_config(self) -> SiteConfig:
        return SiteConfig(
            site_number=str(self.index + 1),
            site_name=self._name_edit.text().strip(),
            direction=self._direction_combo.currentText(),
        )

    def set_site_config(self, config: SiteConfig) -> None:
        self._name_edit.setText(config.site_name)
        idx = self._direction_combo.findText(config.direction)
        if idx >= 0:
            self._direction_combo.setCurrentIndex(idx)


class _TimePeriodRow(QWidget):
    """A single survey time period row: start time — end time + remove button."""

    removed = Signal(object)

    def __init__(self, index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.index = index
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        label = QLabel(f"Period {index + 1}:")
        label.setFixedWidth(70)
        label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        layout.addWidget(label)
        self._label = label

        self._start_time = QTimeEdit()
        self._start_time.setDisplayFormat("HH:mm")
        self._start_time.setTime(QTime(7, 0))
        layout.addWidget(self._start_time)

        dash = QLabel("—")
        dash.setFixedWidth(20)
        dash.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(dash)

        self._end_time = QTimeEdit()
        self._end_time.setDisplayFormat("HH:mm")
        self._end_time.setTime(QTime(19, 0))
        layout.addWidget(self._end_time)

        layout.addStretch()

        self._remove_btn = QPushButton("x")
        self._remove_btn.setFixedSize(24, 24)
        self._remove_btn.setStyleSheet(
            f"QPushButton {{ color: {TEXT_MUTED}; border: 1px solid {BORDER}; "
            f"border-radius: 4px; font-size: 11px; padding: 0; }}"
            f"QPushButton:hover {{ color: {DANGER}; border-color: {DANGER}; }}"
        )
        self._remove_btn.clicked.connect(lambda: self.removed.emit(self))
        layout.addWidget(self._remove_btn)

    def update_index(self, index: int) -> None:
        self.index = index
        self._label.setText(f"Period {index + 1}:")

    def get_times(self) -> tuple[str, str]:
        return (
            self._start_time.time().toString("HH:mm"),
            self._end_time.time().toString("HH:mm"),
        )

    def set_times(self, start: str, end: str) -> None:
        self._start_time.setTime(QTime.fromString(start, "HH:mm"))
        self._end_time.setTime(QTime.fromString(end, "HH:mm"))

    def set_removable(self, removable: bool) -> None:
        """Hide remove button for the first (required) period."""
        self._remove_btn.setVisible(removable)


class JobDetailsWidget(QWidget):
    """Full job details input form (Step 2 of wizard).

    Signals:
        config_ready(JobConfig): Emitted when Continue is clicked and
            validation passes.
        back_requested(): Emitted when Back is clicked.
    """

    config_ready = Signal(object)  # JobConfig
    back_requested = Signal()

    def __init__(
        self,
        module_type: str = "",
        show_classification: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._module_type = module_type
        self._show_classification = show_classification
        self._site_entries: list[_SiteEntry] = []
        self._time_period_rows: list[_TimePeriodRow] = []
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # ── Header ──
        header_row = QHBoxLayout()
        self._back_btn = QPushButton("\u2190  Back")
        self._back_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; color: {TEXT_SECONDARY}; "
            f"font-size: 14px; font-weight: 500; padding: 8px 16px; text-align: left; }}"
            f"QPushButton:hover {{ color: {ACCENT}; }}"
        )
        self._back_btn.clicked.connect(self.back_requested.emit)
        header_row.addWidget(self._back_btn)
        header_row.addStretch()

        title = QLabel("Job Details")
        title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 22px; font-weight: 700; padding: 8px 0;"
        )
        header_row.addWidget(title)
        header_row.addStretch()
        outer.addLayout(header_row)

        # ── Scrollable form ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)

        form_container = QWidget()
        form = QVBoxLayout(form_container)
        form.setSpacing(16)
        form.setContentsMargins(32, 8, 32, 32)

        # ── Job Identity ──
        identity_group = QGroupBox("Job Identity")
        id_layout = QHBoxLayout(identity_group)
        id_layout.setSpacing(12)

        self._job_number = QLineEdit()
        self._job_number.setPlaceholderText("Job Number (e.g. AUQLD13279)")
        self._job_name = QLineEdit()
        self._job_name.setPlaceholderText("Job Name (e.g. Collingwood Park)")

        id_layout.addWidget(QLabel("Job No:"))
        id_layout.addWidget(self._job_number, 1)
        id_layout.addWidget(QLabel("Job Name:"))
        id_layout.addWidget(self._job_name, 2)
        form.addWidget(identity_group)

        # ── Survey Period ──
        period_group = QGroupBox("Survey Period")
        period_layout = QVBoxLayout(period_group)
        period_layout.setSpacing(10)

        # Date row
        date_row = QHBoxLayout()
        date_row.setSpacing(12)

        self._date_range_check = QCheckBox("Date Range")
        self._date_range_check.toggled.connect(self._on_date_range_toggled)

        self._start_date = QDateEdit()
        self._start_date.setCalendarPopup(True)
        self._start_date.setDate(QDate.currentDate())
        self._start_date.setDisplayFormat("yyyy-MM-dd")

        self._end_date = QDateEdit()
        self._end_date.setCalendarPopup(True)
        self._end_date.setDate(QDate.currentDate())
        self._end_date.setDisplayFormat("yyyy-MM-dd")
        self._end_date.setEnabled(False)

        date_row.addWidget(QLabel("Survey Date:"))
        date_row.addWidget(self._start_date)
        date_row.addWidget(self._date_range_check)
        date_row.addWidget(QLabel("End Date:"))
        date_row.addWidget(self._end_date)
        date_row.addStretch()
        period_layout.addLayout(date_row)

        # Time periods section
        time_header = QHBoxLayout()
        time_header.setSpacing(8)
        time_lbl = QLabel("Survey Time Periods:")
        time_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; font-weight: 600;")
        time_header.addWidget(time_lbl)
        time_header.addStretch()

        self._add_time_btn = QPushButton("+ Add Period")
        self._add_time_btn.setFixedWidth(110)
        self._add_time_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_time_btn.clicked.connect(self._add_time_period)
        time_header.addWidget(self._add_time_btn)
        period_layout.addLayout(time_header)

        self._time_periods_container = QVBoxLayout()
        self._time_periods_container.setSpacing(4)
        period_layout.addLayout(self._time_periods_container)

        form.addWidget(period_group)

        # ── Classification (conditionally shown) ──
        self._classification_widget = ClassificationWidget()
        if self._show_classification:
            form.addWidget(self._classification_widget)

        # ── Sites ──
        sites_group = QGroupBox("Survey Sites")
        sites_layout = QVBoxLayout(sites_group)
        sites_layout.setSpacing(8)

        sites_header = QHBoxLayout()
        sites_header.addWidget(QLabel("Number of sites:"))
        self._site_count_spin = QSpinBox()
        self._site_count_spin.setRange(1, 50)
        self._site_count_spin.setValue(1)
        self._site_count_spin.valueChanged.connect(self._on_site_count_changed)
        sites_header.addWidget(self._site_count_spin)
        sites_header.addStretch()

        self._add_site_btn = QPushButton("+ Add Site")
        self._add_site_btn.setObjectName("primary_btn")
        self._add_site_btn.setFixedWidth(120)
        self._add_site_btn.clicked.connect(self._add_site)
        sites_header.addWidget(self._add_site_btn)
        sites_layout.addLayout(sites_header)

        self._sites_container = QVBoxLayout()
        self._sites_container.setSpacing(6)
        sites_layout.addLayout(self._sites_container)
        form.addWidget(sites_group)

        form.addStretch()

        scroll.setWidget(form_container)
        outer.addWidget(scroll, 1)

        # ── Continue button ──
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(32, 8, 32, 16)
        btn_row.addStretch()

        self._continue_btn = QPushButton("Continue  \u2192")
        self._continue_btn.setObjectName("primary_btn")
        self._continue_btn.setMinimumWidth(180)
        self._continue_btn.setMinimumHeight(44)
        self._continue_btn.setStyleSheet(
            self._continue_btn.styleSheet() + "font-size: 15px;"
        )
        self._continue_btn.clicked.connect(self._on_continue)
        btn_row.addWidget(self._continue_btn)
        outer.addLayout(btn_row)

        # Add initial site entry and time period
        self._add_site()
        self._add_time_period()

    # ── Time period management ──

    def _add_time_period(self) -> None:
        row = _TimePeriodRow(len(self._time_period_rows))
        row.removed.connect(self._remove_time_period)
        row.set_removable(len(self._time_period_rows) > 0)  # First row can't be removed
        self._time_period_rows.append(row)
        self._time_periods_container.addWidget(row)

    def _remove_time_period(self, row: _TimePeriodRow) -> None:
        if len(self._time_period_rows) <= 1:
            return
        self._time_periods_container.removeWidget(row)
        self._time_period_rows.remove(row)
        row.deleteLater()
        for i, r in enumerate(self._time_period_rows):
            r.update_index(i)
            r.set_removable(i > 0)

    # ── Site management ──

    def _add_site(self) -> None:
        entry = _SiteEntry(len(self._site_entries))
        entry.removed.connect(self._remove_site)
        self._site_entries.append(entry)
        self._sites_container.addWidget(entry)
        self._site_count_spin.blockSignals(True)
        self._site_count_spin.setValue(len(self._site_entries))
        self._site_count_spin.blockSignals(False)

    def _remove_site(self, entry: _SiteEntry) -> None:
        if len(self._site_entries) <= 1:
            return
        self._sites_container.removeWidget(entry)
        self._site_entries.remove(entry)
        entry.deleteLater()
        # Re-index remaining entries
        for i, e in enumerate(self._site_entries):
            e.update_index(i)
        self._site_count_spin.blockSignals(True)
        self._site_count_spin.setValue(len(self._site_entries))
        self._site_count_spin.blockSignals(False)

    def _on_site_count_changed(self, count: int) -> None:
        while len(self._site_entries) < count:
            self._add_site()
        while len(self._site_entries) > count and len(self._site_entries) > 1:
            entry = self._site_entries[-1]
            self._sites_container.removeWidget(entry)
            self._site_entries.pop()
            entry.deleteLater()

    # ── Date range toggle ──

    def _on_date_range_toggled(self, checked: bool) -> None:
        self._end_date.setEnabled(checked)
        if not checked:
            self._end_date.setDate(self._start_date.date())

    # ── Validation & emit ──

    def _on_continue(self) -> None:
        config = self.get_config()
        # Basic validation
        errors = []
        if not config.job_number:
            errors.append("Job number is required")
        if self._show_classification and not config.classification.active_bins:
            errors.append("At least one vehicle class must be selected")

        if errors:
            # Flash the continue button red briefly
            self._continue_btn.setStyleSheet(
                f"QPushButton {{ background-color: {DANGER}; color: white; "
                f"border-radius: 8px; padding: 10px 22px; font-size: 15px; font-weight: 600; }}"
            )
            self._continue_btn.setText("  ".join(errors))
            from PySide6.QtCore import QTimer
            QTimer.singleShot(2000, self._reset_continue_btn)
            return

        self.config_ready.emit(config)

    def _reset_continue_btn(self) -> None:
        self._continue_btn.setObjectName("primary_btn")
        self._continue_btn.setStyleSheet("")
        self._continue_btn.setText("Continue  \u2192")

    # ── Public API ──

    def get_config(self) -> JobConfig:
        """Build a JobConfig from current form state."""
        start_date = self._start_date.date().toString("yyyy-MM-dd")
        end_date = (
            self._end_date.date().toString("yyyy-MM-dd")
            if self._date_range_check.isChecked()
            else start_date
        )

        sites = [entry.get_site_config() for entry in self._site_entries]

        # Collect time periods
        time_periods = [row.get_times() for row in self._time_period_rows]

        # For backward compat, set start/end time from the first period
        start_time = time_periods[0][0] if time_periods else ""
        end_time = time_periods[0][1] if time_periods else ""

        classification = (
            self._classification_widget.get_config()
            if self._show_classification
            else ClassificationConfig(preset_name="None", active_bins=[], include_pedestrians=False, include_cyclists=False)
        )

        return JobConfig(
            job_number=self._job_number.text().strip(),
            job_name=self._job_name.text().strip(),
            module_type=self._module_type,
            survey_start_date=start_date,
            survey_end_date=end_date,
            survey_start_time=start_time,
            survey_end_time=end_time,
            survey_time_periods=time_periods,
            classification=classification,
            sites=sites,
        )

    def set_config(self, config: JobConfig) -> None:
        """Populate form from a JobConfig (e.g. after folder scan)."""
        self._job_number.setText(config.job_number)
        self._job_name.setText(config.job_name)

        if config.survey_start_date:
            self._start_date.setDate(QDate.fromString(config.survey_start_date, "yyyy-MM-dd"))
        if config.survey_end_date and config.survey_end_date != config.survey_start_date:
            self._date_range_check.setChecked(True)
            self._end_date.setDate(QDate.fromString(config.survey_end_date, "yyyy-MM-dd"))

        if config.survey_start_time:
            self._time_period_rows[0].set_times(config.survey_start_time, config.survey_end_time)

        if self._show_classification:
            self._classification_widget.set_config(config.classification)

        # Set up sites
        while len(self._site_entries) < len(config.sites):
            self._add_site()
        while len(self._site_entries) > len(config.sites) and len(self._site_entries) > 1:
            entry = self._site_entries[-1]
            self._sites_container.removeWidget(entry)
            self._site_entries.pop()
            entry.deleteLater()
        for entry, site_cfg in zip(self._site_entries, config.sites):
            entry.set_site_config(site_cfg)

    def set_from_scan(self, scan_result: dict) -> None:
        """Pre-populate form fields from a folder scan result.

        Parameters
        ----------
        scan_result : dict
            Result from ``JobFolderWidget.get_job_info()`` containing:
            ``job_number``, ``job_name``, ``sites_summary``, ``all_dates``.
        """
        # Job identity
        job_number = scan_result.get("job_number", "")
        job_name = scan_result.get("job_name", "")
        if job_number:
            self._job_number.setText(job_number)
        if job_name:
            self._job_name.setText(job_name)

        # Dates from scan
        all_dates = scan_result.get("all_dates", [])
        if all_dates:
            def _to_qdate(date_str: str) -> QDate:
                parts = date_str.split("_")
                return QDate(int(parts[0]), int(parts[1]), int(parts[2]))

            earliest = _to_qdate(all_dates[0])
            latest = _to_qdate(all_dates[-1])
            self._start_date.setDate(earliest)

            if len(all_dates) > 1 and all_dates[0] != all_dates[-1]:
                self._date_range_check.setChecked(True)
                self._end_date.setDate(latest)

        # Sites from scan
        sites_summary = scan_result.get("sites_summary", [])
        if sites_summary:
            # Clear existing and create new entries
            while len(self._site_entries) > 1:
                entry = self._site_entries[-1]
                self._sites_container.removeWidget(entry)
                self._site_entries.pop()
                entry.deleteLater()

            for i, site_info in enumerate(sites_summary):
                if i == 0:
                    # Use the existing first entry
                    entry = self._site_entries[0]
                else:
                    self._add_site()
                    entry = self._site_entries[-1]

                config = SiteConfig(
                    site_number=site_info.get("site_id", ""),
                    site_name=site_info.get("site_name", ""),
                    direction=site_info.get("direction", ""),
                )
                entry.set_site_config(config)

            self._site_count_spin.blockSignals(True)
            self._site_count_spin.setValue(len(self._site_entries))
            self._site_count_spin.blockSignals(False)

    def set_module_type(self, module_type: str) -> None:
        """Set the module type (affects which fields are shown)."""
        self._module_type = module_type

    def set_job_number(self, number: str) -> None:
        """Programmatically set job number (from folder scan)."""
        self._job_number.setText(number)
