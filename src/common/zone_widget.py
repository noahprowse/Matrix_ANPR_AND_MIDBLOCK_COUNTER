"""Polygon zone drawing for capture zones and exclusion zones.

Provides overlay drawing on video preview widgets and a control panel
for managing zones used by ANPR and Counter modules.
"""

import cv2
import numpy as np
from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Signal, Qt, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QPolygon, QMouseEvent

from src.common.theme import (
    TEXT_MUTED,
    SUCCESS,
    ACCENT,
    BORDER,
    DARK_CARD,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

# ── Zone geometry helpers ──────────────────────────────────────────────


def point_in_any_zone(cx: int, cy: int, zones: list) -> bool:
    """Check if point is inside any of the given polygon zones.

    Args:
        cx: X coordinate of the point.
        cy: Y coordinate of the point.
        zones: List of zones, each zone is a list of (x, y) tuples.

    Returns:
        True if the point falls inside at least one zone.
    """
    for zone in zones:
        if len(zone) < 3:
            continue
        contour = np.array(zone, dtype=np.int32)
        result = cv2.pointPolygonTest(contour, (float(cx), float(cy)), False)
        if result >= 0:
            return True
    return False


def should_process_detection(
    cx: int,
    cy: int,
    capture_zones: list,
    exclusion_zones: list,
) -> bool:
    """Decide whether a detection at (cx, cy) should be processed.

    Rules:
        - If capture zones are defined the point must be inside at least one.
        - If exclusion zones are defined the point must not be inside any.
        - If no zones are defined the detection is always processed.

    Returns:
        True if the detection should be kept.
    """
    if exclusion_zones and point_in_any_zone(cx, cy, exclusion_zones):
        return False
    if capture_zones and not point_in_any_zone(cx, cy, capture_zones):
        return False
    return True


def draw_zones_on_frame(
    frame: np.ndarray,
    capture_zones: list,
    exclusion_zones: list,
) -> np.ndarray:
    """Draw semi-transparent zone overlays on a BGR frame.

    Capture zones are drawn in green, exclusion zones in red.
    Returns a *copy* of the frame with overlays composited.
    """
    overlay = frame.copy()

    for idx, zone in enumerate(capture_zones):
        if len(zone) < 3:
            continue
        pts = np.array(zone, dtype=np.int32)
        cv2.fillPoly(overlay, [pts], (0, 180, 0))  # green fill
        cv2.polylines(frame, [pts], isClosed=True, color=(0, 220, 0), thickness=2)
        # Label
        cx = int(np.mean([p[0] for p in zone]))
        cy = int(np.mean([p[1] for p in zone]))
        label = f"Capture {idx + 1}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(
            frame,
            (cx - tw // 2 - 4, cy - th - 6),
            (cx + tw // 2 + 4, cy + 4),
            (0, 0, 0),
            -1,
        )
        cv2.putText(
            frame, label, (cx - tw // 2, cy),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 0), 2,
        )

    for idx, zone in enumerate(exclusion_zones):
        if len(zone) < 3:
            continue
        pts = np.array(zone, dtype=np.int32)
        cv2.fillPoly(overlay, [pts], (0, 0, 180))  # red fill
        cv2.polylines(frame, [pts], isClosed=True, color=(0, 0, 220), thickness=2)
        cx = int(np.mean([p[0] for p in zone]))
        cy = int(np.mean([p[1] for p in zone]))
        label = f"Exclusion {idx + 1}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(
            frame,
            (cx - tw // 2 - 4, cy - th - 6),
            (cx + tw // 2 + 4, cy + 4),
            (0, 0, 0),
            -1,
        )
        cv2.putText(
            frame, label, (cx - tw // 2, cy),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 220), 2,
        )

    # Blend the filled overlay at 35% opacity
    result = cv2.addWeighted(overlay, 0.35, frame, 0.65, 0)
    return result


# ── Zone overlay mixin for video preview widgets ──────────────────────

_CLOSE_THRESHOLD_PX = 15


class ZoneOverlay:
    """Mixin that adds polygon zone drawing to a QLabel-based preview widget.

    Usage::

        class MyPreview(ZoneOverlay, VideoPreviewWidget):
            pass

    The host widget must be a QLabel (or subclass).  Call
    ``start_zone_drawing(zone_type)`` to enter drawing mode and connect to
    ``zone_completed`` to receive the finished polygon.
    """

    # Emitted with (zone_type, [(x,y), ...]) when a polygon is closed.
    # Needs to be defined on the concrete class; see _ensure_signals().

    def zone_overlay_init(self):
        """Call from __init__ of the concrete class after super().__init__."""
        self._drawing_active = False
        self._zone_type: str = ""  # "capture" or "exclusion"
        self._current_points: list[tuple[int, int]] = []
        self._capture_zones: list[list[tuple[int, int]]] = []
        self._exclusion_zones: list[list[tuple[int, int]]] = []
        self._frame_size: tuple[int, int] | None = None  # (w, h) of source frame
        self.setMouseTracking(True)
        self._mouse_pos: QPoint | None = None

    # ── public API ────────────────────────────────────────────────

    def start_zone_drawing(self, zone_type: str):
        """Begin drawing a new zone ('capture' or 'exclusion')."""
        self._drawing_active = True
        self._zone_type = zone_type
        self._current_points = []
        self.setCursor(Qt.CursorShape.CrossCursor)

    def cancel_zone_drawing(self):
        self._drawing_active = False
        self._current_points = []
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    def set_zones(self, capture_zones: list, exclusion_zones: list):
        self._capture_zones = [list(z) for z in capture_zones]
        self._exclusion_zones = [list(z) for z in exclusion_zones]
        self.update()

    def set_frame_size(self, width: int, height: int):
        """Store the native frame resolution for coordinate mapping."""
        self._frame_size = (width, height)

    # ── coordinate mapping ────────────────────────────────────────

    def _widget_to_frame(self, pos: QPoint) -> tuple[int, int] | None:
        """Map a widget-local position to frame pixel coordinates."""
        pixmap = self.pixmap()
        if pixmap is None or self._frame_size is None:
            return None
        fw, fh = self._frame_size
        pw, ph = pixmap.width(), pixmap.height()
        # The pixmap is centered inside the label
        ox = (self.width() - pw) // 2
        oy = (self.height() - ph) // 2
        lx = pos.x() - ox
        ly = pos.y() - oy
        if lx < 0 or ly < 0 or lx >= pw or ly >= ph:
            return None
        fx = int(lx * fw / pw)
        fy = int(ly * fh / ph)
        return (fx, fy)

    def _frame_to_widget(self, fx: int, fy: int) -> QPoint:
        """Map frame pixel coordinates back to widget coordinates."""
        pixmap = self.pixmap()
        if pixmap is None or self._frame_size is None:
            return QPoint(0, 0)
        fw, fh = self._frame_size
        pw, ph = pixmap.width(), pixmap.height()
        ox = (self.width() - pw) // 2
        oy = (self.height() - ph) // 2
        wx = int(fx * pw / fw) + ox
        wy = int(fy * ph / fh) + oy
        return QPoint(wx, wy)

    # ── mouse events ──────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        if not self._drawing_active:
            super().mousePressEvent(event)
            return

        if event.button() == Qt.MouseButton.LeftButton:
            pt = self._widget_to_frame(event.pos())
            if pt is None:
                return
            # Check if clicking near first vertex to close polygon
            if len(self._current_points) >= 3:
                first = self._frame_to_widget(*self._current_points[0])
                if (event.pos() - first).manhattanLength() < _CLOSE_THRESHOLD_PX * 2:
                    self._close_polygon()
                    return
            self._current_points.append(pt)
            self.update()

        elif event.button() == Qt.MouseButton.RightButton:
            if len(self._current_points) >= 3:
                self._close_polygon()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drawing_active:
            self._mouse_pos = event.pos()
            self.update()
        super().mouseMoveEvent(event)

    # ── polygon completion ────────────────────────────────────────

    def _close_polygon(self):
        zone = list(self._current_points)
        zone_type = self._zone_type
        self._drawing_active = False
        self._current_points = []
        self.setCursor(Qt.CursorShape.ArrowCursor)
        if zone_type == "capture":
            self._capture_zones.append(zone)
        else:
            self._exclusion_zones.append(zone)
        self.update()
        # Emit signal if the concrete class defines it
        if hasattr(self, "zone_completed"):
            self.zone_completed.emit(zone_type, zone)

    # ── painting ──────────────────────────────────────────────────

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw completed capture zones
        for idx, zone in enumerate(self._capture_zones):
            self._paint_zone(painter, zone, QColor(46, 204, 113, 70), QColor(46, 204, 113), f"Capture {idx + 1}")

        # Draw completed exclusion zones
        for idx, zone in enumerate(self._exclusion_zones):
            self._paint_zone(painter, zone, QColor(231, 76, 60, 70), QColor(231, 76, 60), f"Exclusion {idx + 1}")

        # Draw in-progress polygon
        if self._drawing_active and self._current_points:
            color = QColor(46, 204, 113) if self._zone_type == "capture" else QColor(231, 76, 60)
            pen = QPen(color, 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            pts = [self._frame_to_widget(*p) for p in self._current_points]
            for i in range(len(pts) - 1):
                painter.drawLine(pts[i], pts[i + 1])
            # Rubber-band line to mouse
            if self._mouse_pos is not None and pts:
                painter.drawLine(pts[-1], self._mouse_pos)
            # Draw vertices
            painter.setBrush(color)
            for i, pt in enumerate(pts):
                radius = 6 if i == 0 else 4
                painter.drawEllipse(pt, radius, radius)

        painter.end()

    def _paint_zone(self, painter: QPainter, zone: list, fill: QColor, outline: QColor, label: str):
        if len(zone) < 3:
            return
        pts = [self._frame_to_widget(*p) for p in zone]
        polygon = QPolygon(pts)
        painter.setBrush(fill)
        painter.setPen(QPen(outline, 2))
        painter.drawPolygon(polygon)
        # Label at centroid
        cx = sum(p.x() for p in pts) // len(pts)
        cy = sum(p.y() for p in pts) // len(pts)
        painter.setPen(QPen(Qt.GlobalColor.white))
        painter.drawText(cx - 30, cy, label)


# ── Zone control panel ────────────────────────────────────────────────


class ZoneControlWidget(QGroupBox):
    """Control panel for adding / removing capture and exclusion zones."""

    zone_draw_requested = Signal(str)  # "capture" or "exclusion"
    zones_changed = Signal()

    def __init__(self, parent=None):
        super().__init__("Zone Configuration", parent)
        self._capture_zones: list[list[tuple[int, int]]] = []
        self._exclusion_zones: list[list[tuple[int, int]]] = []
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Buttons row 1 – add zones
        row1 = QHBoxLayout()
        self._btn_add_capture = QPushButton("Add Capture Zone")
        self._btn_add_capture.setStyleSheet(
            f"QPushButton {{ border: 1px solid {SUCCESS}; }} "
            f"QPushButton:hover {{ background-color: {SUCCESS}; }}"
        )
        self._btn_add_capture.clicked.connect(lambda: self._request_draw("capture"))
        row1.addWidget(self._btn_add_capture)

        self._btn_add_exclusion = QPushButton("Add Exclusion Zone")
        self._btn_add_exclusion.setStyleSheet(
            f"QPushButton {{ border: 1px solid {ACCENT}; }} "
            f"QPushButton:hover {{ background-color: {ACCENT}; }}"
        )
        self._btn_add_exclusion.clicked.connect(lambda: self._request_draw("exclusion"))
        row1.addWidget(self._btn_add_exclusion)
        layout.addLayout(row1)

        # Buttons row 2 – remove / clear
        row2 = QHBoxLayout()
        self._btn_remove_last = QPushButton("Remove Last Zone")
        self._btn_remove_last.clicked.connect(self._remove_last)
        row2.addWidget(self._btn_remove_last)

        self._btn_clear = QPushButton("Clear All Zones")
        self._btn_clear.clicked.connect(self._clear_all)
        row2.addWidget(self._btn_clear)
        layout.addLayout(row2)

        # Status label
        self._lbl_status = QLabel()
        self._lbl_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        layout.addWidget(self._lbl_status)

        self._update_status()

    # ── public API ────────────────────────────────────────────────

    @property
    def capture_zones(self) -> list[list[tuple[int, int]]]:
        return list(self._capture_zones)

    @property
    def exclusion_zones(self) -> list[list[tuple[int, int]]]:
        return list(self._exclusion_zones)

    def add_zone(self, zone_type: str, points: list[tuple[int, int]]):
        """Programmatically add a completed zone."""
        if zone_type == "capture":
            self._capture_zones.append(list(points))
        else:
            self._exclusion_zones.append(list(points))
        self._update_status()
        self.zones_changed.emit()

    def get_all_zones(self) -> dict:
        """Return zones as a serialisable dict."""
        return {
            "capture": [list(z) for z in self._capture_zones],
            "exclusion": [list(z) for z in self._exclusion_zones],
        }

    def set_zones(self, capture: list, exclusion: list):
        """Restore zones (e.g. from saved config)."""
        self._capture_zones = [list(z) for z in capture]
        self._exclusion_zones = [list(z) for z in exclusion]
        self._update_status()
        self.zones_changed.emit()

    # ── slots ─────────────────────────────────────────────────────

    def _request_draw(self, zone_type: str):
        self.zone_draw_requested.emit(zone_type)

    def _remove_last(self):
        if self._exclusion_zones:
            self._exclusion_zones.pop()
        elif self._capture_zones:
            self._capture_zones.pop()
        else:
            return
        self._update_status()
        self.zones_changed.emit()

    def _clear_all(self):
        if not self._capture_zones and not self._exclusion_zones:
            return
        self._capture_zones.clear()
        self._exclusion_zones.clear()
        self._update_status()
        self.zones_changed.emit()

    # ── helpers ───────────────────────────────────────────────────

    def _update_status(self):
        nc = len(self._capture_zones)
        ne = len(self._exclusion_zones)
        total = nc + ne
        if total == 0:
            self._lbl_status.setText("No zones defined (full frame will be used)")
        else:
            parts = []
            if nc:
                parts.append(f"{nc} capture")
            if ne:
                parts.append(f"{ne} exclusion")
            self._lbl_status.setText(f"Zones: {', '.join(parts)} ({total} total)")
