"""Extraction time window filter widget."""

from datetime import time

from PySide6.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QCheckBox,
    QTimeEdit,
)
from PySide6.QtCore import QTime

from src.common.theme import TEXT_SECONDARY, TEXT_MUTED


class TimeFilterWidget(QGroupBox):
    """Widget for setting an extraction time window.

    When enabled, only frames within the start-end window are processed.
    Times can be auto-populated from video overlay OCR.
    """

    def __init__(self, parent=None):
        super().__init__("Extraction Time Filter", parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        self.enabled_cb = QCheckBox("Filter by time window")
        self.enabled_cb.setChecked(False)
        self.enabled_cb.toggled.connect(self._on_toggle)
        layout.addWidget(self.enabled_cb)

        # Time inputs row
        time_row = QHBoxLayout()

        start_col = QVBoxLayout()
        lbl = QLabel("Start:")
        lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        self.start_time = QTimeEdit()
        self.start_time.setDisplayFormat("HH:mm")
        self.start_time.setTime(QTime(7, 0))
        self.start_time.setEnabled(False)
        self.start_time.timeChanged.connect(self._on_time_changed)
        start_col.addWidget(lbl)
        start_col.addWidget(self.start_time)
        time_row.addLayout(start_col)

        end_col = QVBoxLayout()
        lbl = QLabel("End:")
        lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        self.end_time = QTimeEdit()
        self.end_time.setDisplayFormat("HH:mm")
        self.end_time.setTime(QTime(19, 0))
        self.end_time.setEnabled(False)
        self.end_time.timeChanged.connect(self._on_time_changed)
        end_col.addWidget(lbl)
        end_col.addWidget(self.end_time)
        time_row.addLayout(end_col)

        layout.addLayout(time_row)

        self.info_label = QLabel("All video data will be processed")
        self.info_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

    def _on_toggle(self, enabled: bool):
        self.start_time.setEnabled(enabled)
        self.end_time.setEnabled(enabled)
        self._update_info_text()

    def _on_time_changed(self):
        if self.enabled_cb.isChecked():
            self._update_info_text()

    def _update_info_text(self):
        if self.enabled_cb.isChecked():
            s = self.start_time.time().toString("HH:mm")
            e = self.end_time.time().toString("HH:mm")
            self.info_label.setText(f"Only processing {s} to {e}")
        else:
            self.info_label.setText("All video data will be processed")

    def set_times(self, start_str: str | None, end_str: str | None):
        """Auto-populate times from detected video timestamps."""
        if start_str:
            parts = start_str.split(":")
            if len(parts) >= 2:
                self.start_time.setTime(QTime(int(parts[0]), int(parts[1])))
        if end_str:
            parts = end_str.split(":")
            if len(parts) >= 2:
                self.end_time.setTime(QTime(int(parts[0]), int(parts[1])))

    def get_filter(self) -> tuple[time, time] | None:
        """Return the time filter window, or None if disabled."""
        if not self.enabled_cb.isChecked():
            return None

        qt_start = self.start_time.time()
        qt_end = self.end_time.time()
        return (
            time(qt_start.hour(), qt_start.minute()),
            time(qt_end.hour(), qt_end.minute()),
        )
