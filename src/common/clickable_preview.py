"""Reusable video preview widget with line drawing, calibration, and zone overlay.

Extracted from counter_page.py so that both the midblock counter and pedestrian
counter modules can share the same interactive preview component.
"""

import cv2
from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QImage, QPixmap, QMouseEvent

from src.common.theme import (
    TEXT_MUTED,
    STEP_ACTIVE,
    STEP_INACTIVE,
    STEP_COMPLETED,
)
from src.common.zone_widget import ZoneOverlay, draw_zones_on_frame

# Distinct colors for each count line (BGR for OpenCV)
LINE_COLORS_BGR = [
    (0, 0, 255),     # Red
    (255, 0, 0),     # Blue
    (0, 200, 0),     # Green
    (0, 200, 255),   # Orange
    (255, 0, 255),   # Magenta
    (255, 255, 0),   # Cyan
    (128, 0, 255),   # Purple
    (0, 255, 255),   # Yellow
]


class ClickablePreview(ZoneOverlay, QLabel):
    """Video preview that supports drawing count lines, speed calibration, and zones."""

    line_added = Signal(dict)
    calibration_done = Signal(tuple, tuple)
    zone_completed = Signal(str, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.zone_overlay_init()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(640, 360)
        self.setStyleSheet("background-color: #F1F3F5; border-radius: 8px;")
        self.setText("No video loaded")
        self.setCursor(Qt.CursorShape.CrossCursor)

        self._first_frame = None
        self._video_size = None
        self._click_start = None

        # Drawing modes
        self._mode = "idle"  # "idle", "drawing_line", "calibrating"
        self._pending_label = ""
        self._calibration_callback = None
        self._calibration_points = []

        # Multiple lines: list of {start, end, label, color_bgr}
        self.lines: list[dict] = []

    def set_frame(self, frame):
        self._first_frame = frame.copy()
        h, w = frame.shape[:2]
        self._video_size = (w, h)
        self.set_frame_size(w, h)
        self._redraw()

    def _display_frame(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)
        scaled = pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)

    def update_display_frame(self, qimg: QImage):
        pixmap = QPixmap.fromImage(qimg)
        scaled = pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)

    def start_drawing(self, label: str):
        """Enable line drawing mode."""
        self._mode = "drawing_line"
        self._pending_label = label
        self._click_start = None
        self._redraw()

    def start_calibration(self, callback):
        """Enable calibration mode -- user clicks two points."""
        self._mode = "calibrating"
        self._calibration_callback = callback
        self._calibration_points = []
        self._redraw()

    def cancel_drawing(self):
        self._mode = "idle"
        self._click_start = None
        self._calibration_points = []
        self._redraw()

    def mousePressEvent(self, event: QMouseEvent):
        if self._drawing_active:
            ZoneOverlay.mousePressEvent(self, event)
            return

        if self._mode == "idle" or self._first_frame is None:
            return

        video_point = self._widget_to_video(event.position().x(), event.position().y())
        if video_point is None:
            return

        if self._mode == "drawing_line":
            self._handle_line_click(video_point)
        elif self._mode == "calibrating":
            self._handle_calibration_click(video_point)

    def _handle_line_click(self, point):
        if self._click_start is None:
            self._click_start = point
            self._redraw()
        else:
            color = LINE_COLORS_BGR[len(self.lines) % len(LINE_COLORS_BGR)]
            line = {
                "start": self._click_start,
                "end": point,
                "label": self._pending_label,
                "color_bgr": color,
            }
            self.lines.append(line)
            self._click_start = None
            self._mode = "idle"
            self._redraw()
            self.line_added.emit(line)

    def _handle_calibration_click(self, point):
        self._calibration_points.append(point)
        self._redraw()

        if len(self._calibration_points) == 2:
            p1, p2 = self._calibration_points
            self._mode = "idle"
            self._calibration_points = []
            self._redraw()
            if self._calibration_callback:
                self._calibration_callback(p1, p2)

    def _widget_to_video(self, wx: float, wy: float) -> tuple[int, int] | None:
        if not self.pixmap() or self._video_size is None:
            return None
        pm = self.pixmap()
        pw, ph = pm.width(), pm.height()
        lw, lh = self.width(), self.height()
        ox = (lw - pw) / 2
        oy = (lh - ph) / 2
        px = wx - ox
        py = wy - oy
        if px < 0 or py < 0 or px > pw or py > ph:
            return None
        vw, vh = self._video_size
        return (int(px * vw / pw), int(py * vh / ph))

    def _redraw(self):
        """Redraw the first frame with all lines and any in-progress state."""
        if self._first_frame is None:
            return

        frame = self._first_frame.copy()

        # Draw zones on the frame
        if self._capture_zones or self._exclusion_zones:
            frame = draw_zones_on_frame(frame, self._capture_zones, self._exclusion_zones)

        # Draw completed lines
        for line in self.lines:
            color = line["color_bgr"]
            cv2.line(frame, line["start"], line["end"], color, 3)
            cv2.circle(frame, line["start"], 5, color, -1)
            cv2.circle(frame, line["end"], 5, color, -1)
            mx = (line["start"][0] + line["end"][0]) // 2
            my = (line["start"][1] + line["end"][1]) // 2
            cv2.putText(
                frame, line["label"],
                (mx - 40, my - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2,
            )

        # Draw in-progress line
        if self._mode == "drawing_line" and self._click_start is not None:
            cv2.circle(frame, self._click_start, 8, (0, 0, 255), -1)
            cv2.putText(
                frame, f"Drawing: {self._pending_label} - click to set end",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2,
            )

        # Draw calibration points
        if self._mode == "calibrating":
            for pt in self._calibration_points:
                cv2.circle(frame, pt, 8, (0, 255, 255), -1)
            msg = "Calibrating: click 2 points of known distance"
            if len(self._calibration_points) == 1:
                msg = "Calibrating: click second point"
            cv2.putText(
                frame, msg,
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2,
            )

        self._display_frame(frame)

    def remove_last_line(self):
        if self.lines:
            self.lines.pop()
            self._redraw()

    def clear_all_lines(self):
        self.lines.clear()
        self._click_start = None
        self._mode = "idle"
        self._redraw()

    def get_lines(self) -> list[dict]:
        return self.lines

    def resizeEvent(self, event):
        """Redraw on resize so the preview stays sharp."""
        super().resizeEvent(event)
        self._redraw()


class StepIndicator(QWidget):
    """Horizontal step indicator: Step 1  *  Step 2  *  Step 3."""

    def __init__(self, labels: list[str], parent=None):
        super().__init__(parent)
        self._labels = labels
        self._step_labels: list[QLabel] = []
        self._dot_labels: list[QLabel] = []
        self._build_ui()
        self.set_current(0)

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.addStretch()

        for i, text in enumerate(self._labels):
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._step_labels.append(lbl)
            layout.addWidget(lbl)

            if i < len(self._labels) - 1:
                dot = QLabel("  \u2022  ")
                dot.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 14px;")
                self._dot_labels.append(dot)
                layout.addWidget(dot)

        layout.addStretch()

    def set_current(self, index: int):
        for i, lbl in enumerate(self._step_labels):
            if i < index:
                lbl.setStyleSheet(STEP_COMPLETED)
            elif i == index:
                lbl.setStyleSheet(STEP_ACTIVE)
            else:
                lbl.setStyleSheet(STEP_INACTIVE)
