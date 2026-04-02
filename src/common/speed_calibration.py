"""Speed calibration widget for the midblock counter module."""

import math
from dataclasses import dataclass

from PySide6.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QCheckBox,
    QPushButton,
    QDoubleSpinBox,
)
from PySide6.QtCore import Qt

from src.common.theme import TEXT_SECONDARY, TEXT_MUTED, SUCCESS


@dataclass
class SpeedCalibration:
    """Speed estimation calibration data."""
    enabled: bool = False
    pixels_per_meter: float = 0.0
    point1: tuple[int, int] = (0, 0)
    point2: tuple[int, int] = (0, 0)
    real_distance_m: float = 3.5


class SpeedCalibrationWidget(QGroupBox):
    """Widget for speed estimation calibration.

    User clicks two points on the video preview and enters the
    real-world distance between them (e.g., lane width = 3.5 m).
    """

    def __init__(self, parent=None):
        super().__init__("Speed Estimation", parent)
        self._calibration = SpeedCalibration()
        self._calibrate_callback = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        self.enabled_cb = QCheckBox("Enable speed estimation")
        self.enabled_cb.setChecked(False)
        self.enabled_cb.setToolTip(
            "Estimates vehicle speed from tracked movement.\n"
            "Requires calibration: click two points of known distance."
        )
        self.enabled_cb.toggled.connect(self._on_toggle)
        layout.addWidget(self.enabled_cb)

        # Distance input — using QDoubleSpinBox for validation
        dist_row = QHBoxLayout()
        lbl = QLabel("Reference distance (m):")
        lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        self.distance_input = QDoubleSpinBox()
        self.distance_input.setRange(0.5, 200.0)
        self.distance_input.setValue(3.5)
        self.distance_input.setSuffix(" m")
        self.distance_input.setDecimals(1)
        self.distance_input.setSingleStep(0.5)
        self.distance_input.setFixedWidth(100)
        self.distance_input.setEnabled(False)
        dist_row.addWidget(lbl)
        dist_row.addWidget(self.distance_input)
        dist_row.addStretch()
        layout.addLayout(dist_row)

        # Calibrate button
        self.calibrate_btn = QPushButton("Calibrate (click 2 points on video)")
        self.calibrate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.calibrate_btn.setEnabled(False)
        self.calibrate_btn.clicked.connect(self._on_calibrate)
        layout.addWidget(self.calibrate_btn)

        self.status_label = QLabel("Speed estimation disabled")
        self.status_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

    def _on_toggle(self, enabled: bool):
        self.distance_input.setEnabled(enabled)
        self.calibrate_btn.setEnabled(enabled)
        if not enabled:
            self._calibration.enabled = False
            self.status_label.setText("Speed estimation disabled")
            self.status_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")

    def set_calibrate_callback(self, callback):
        """Set callback that starts calibration mode on the preview.

        The callback should accept a function(point1, point2) that
        will be called when the user clicks two points.
        """
        self._calibrate_callback = callback

    def _on_calibrate(self):
        if self._calibrate_callback:
            self.status_label.setText("Click two points on the video (e.g., lane edges)...")
            self.status_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px;")
            self._calibrate_callback(self._on_calibration_done)

    def _on_calibration_done(self, point1: tuple[int, int], point2: tuple[int, int]):
        """Called when user finishes clicking two calibration points."""
        real_dist = self.distance_input.value()

        pixel_dist = math.sqrt(
            (point2[0] - point1[0]) ** 2 + (point2[1] - point1[1]) ** 2
        )

        if pixel_dist < 1 or real_dist <= 0:
            self.status_label.setText("Calibration failed — points too close")
            return

        ppm = pixel_dist / real_dist

        self._calibration = SpeedCalibration(
            enabled=True,
            pixels_per_meter=ppm,
            point1=point1,
            point2=point2,
            real_distance_m=real_dist,
        )

        self.status_label.setText(
            f"Calibrated: {ppm:.1f} px/m  ({real_dist}m = {pixel_dist:.0f}px)"
        )
        self.status_label.setStyleSheet(f"color: {SUCCESS}; font-size: 10px;")

    def get_calibration(self) -> SpeedCalibration | None:
        """Return calibration data, or None if disabled/uncalibrated."""
        if not self.enabled_cb.isChecked():
            return None
        if self._calibration.pixels_per_meter <= 0:
            return None
        return self._calibration
