"""PySide6 3-step wizard page for Intersection Turning Movement Counting.

Step 1: Job details (JobDetailsWidget)
Step 2: Zone definition with video preview and polygon drawing
Step 3: Processing dashboard with live O-D matrix and TMC summary
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import cv2
import numpy as np
from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtGui import QColor, QFont, QImage, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.common.data_models import (
    JobConfig,
    NamedZone,
    VideoAssignment,
)
from src.common.job_details_widget import JobDetailsWidget
from src.common.theme import (
    ACCENT,
    ACCENT_LIGHT,
    BACK_BUTTON_STYLE,
    BG_PRIMARY,
    BG_SECONDARY,
    BORDER,
    DANGER,
    SECTION_HEADER,
    STEP_ACTIVE,
    STEP_COMPLETED,
    STEP_INACTIVE,
    SUCCESS,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from src.common.zone_widget import ZoneOverlay, draw_zones_on_frame
from src.engine.monitor_bridge import MonitorBridge
from src.engine.process_manager import ProcessManager
from src.engine.processing_dashboard import ProcessingDashboard
from src.intersection.intersection_export import IntersectionExporter
from src.intersection.od_matrix import ODMatrix
from src.intersection.tmc_calculator import TMCCalculator, MOVEMENT_ORDER

logger = logging.getLogger(__name__)

# Zone colors (BGR) for up to 8 zones
_ZONE_COLORS_BGR = [
    (0, 200, 0),     # Green
    (0, 0, 255),     # Red
    (255, 0, 0),     # Blue
    (0, 200, 255),   # Orange
    (255, 0, 255),   # Magenta
    (255, 255, 0),   # Cyan
    (128, 0, 255),   # Purple
    (0, 255, 255),   # Yellow
]

_COMPASS_DIRECTIONS = ["N", "S", "E", "W", "NE", "NW", "SE", "SW"]


# ── Zone preview widget with polygon drawing ──────────────────────────


class _ZonePreview(ZoneOverlay, QLabel):
    """Video preview label with zone polygon drawing capability."""

    zone_completed = Signal(str, list)  # zone_type, [(x,y), ...]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.zone_overlay_init()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(640, 400)
        self.setStyleSheet(
            f"background-color: {BG_SECONDARY}; border: 1px solid {BORDER}; "
            f"border-radius: 8px;"
        )
        self.setText("Load a reference frame to begin")

        self._reference_frame: Optional[np.ndarray] = None
        self._video_size: Optional[tuple[int, int]] = None
        self._named_zones: list[NamedZone] = []

    def set_reference_frame(self, frame: np.ndarray) -> None:
        """Set the reference frame from video."""
        self._reference_frame = frame.copy()
        h, w = frame.shape[:2]
        self._video_size = (w, h)
        self.set_frame_size(w, h)
        self._redraw()

    def set_named_zones(self, zones: list[NamedZone]) -> None:
        """Update the list of named zones to render."""
        self._named_zones = list(zones)
        self._redraw()

    def _redraw(self) -> None:
        """Redraw the reference frame with all zone overlays."""
        if self._reference_frame is None:
            return

        frame = self._reference_frame.copy()

        # Draw named zones
        for zone in self._named_zones:
            if len(zone.polygon) < 3:
                continue
            pts = np.array(zone.polygon, dtype=np.int32)
            color = zone.color_bgr

            # Semi-transparent fill
            overlay = frame.copy()
            cv2.fillPoly(overlay, [pts], color)
            frame = cv2.addWeighted(overlay, 0.3, frame, 0.7, 0)

            # Outline
            cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=2)

            # Label at centroid
            cx = int(np.mean([p[0] for p in zone.polygon]))
            cy = int(np.mean([p[1] for p in zone.polygon]))
            label = zone.name
            if zone.approach:
                label += f" ({zone.approach})"
            (tw, th), _ = cv2.getTextSize(
                label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
            )
            cv2.rectangle(
                frame,
                (cx - tw // 2 - 4, cy - th - 6),
                (cx + tw // 2 + 4, cy + 4),
                (0, 0, 0),
                -1,
            )
            cv2.putText(
                frame,
                label,
                (cx - tw // 2, cy),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2,
            )

        # Convert to QPixmap and display
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

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._redraw()


# ── Step 2: Zone Definition Page ──────────────────────────────────────


class _ZoneDefinitionPage(QWidget):
    """Zone definition step with video preview and zone drawing tools."""

    zones_ready = Signal(list)  # list[NamedZone]
    back_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._zones: list[NamedZone] = []
        self._video_paths: list[str] = []
        self._drawing_zone_index: int = -1
        self._build_ui()

    def set_video_paths(self, paths: list[str]) -> None:
        """Store the video paths from Step 1 config."""
        self._video_paths = list(paths)

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 16)
        layout.setSpacing(16)

        # ── Left: Video preview ──
        self._preview = _ZonePreview()
        self._preview.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._preview.zone_completed.connect(self._on_polygon_completed)
        layout.addWidget(self._preview, stretch=3)

        # ── Right: Controls ──
        right_panel = QScrollArea()
        right_panel.setWidgetResizable(True)
        right_panel.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        right_inner = QWidget()
        controls = QVBoxLayout(right_inner)
        controls.setSpacing(10)

        # Load reference frame
        self._load_frame_btn = QPushButton("Load Reference Frame")
        self._load_frame_btn.setObjectName("primary_btn")
        self._load_frame_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._load_frame_btn.clicked.connect(self._load_reference_frame)
        controls.addWidget(self._load_frame_btn)

        # Zone list
        zone_group = QGroupBox("Intersection Zones")
        zone_layout = QVBoxLayout(zone_group)

        self._zone_list = QListWidget()
        self._zone_list.setMaximumHeight(200)
        zone_layout.addWidget(self._zone_list)

        # Add zone buttons
        add_row = QHBoxLayout()
        self._add_entry_btn = QPushButton("+ Entry Zone")
        self._add_entry_btn.setStyleSheet(
            f"QPushButton {{ border: 1px solid {SUCCESS}; }}"
            f"QPushButton:hover {{ background-color: {SUCCESS}; color: white; }}"
        )
        self._add_entry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_entry_btn.clicked.connect(lambda: self._add_zone("entry"))
        add_row.addWidget(self._add_entry_btn)

        self._add_exit_btn = QPushButton("+ Exit Zone")
        self._add_exit_btn.setStyleSheet(
            f"QPushButton {{ border: 1px solid {ACCENT}; }}"
            f"QPushButton:hover {{ background-color: {ACCENT}; color: white; }}"
        )
        self._add_exit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_exit_btn.clicked.connect(lambda: self._add_zone("exit"))
        add_row.addWidget(self._add_exit_btn)
        zone_layout.addLayout(add_row)

        # Remove zone
        remove_row = QHBoxLayout()
        self._remove_btn = QPushButton("Remove Selected")
        self._remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._remove_btn.clicked.connect(self._remove_selected_zone)
        remove_row.addWidget(self._remove_btn)

        self._clear_btn = QPushButton("Clear All")
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.clicked.connect(self._clear_all_zones)
        remove_row.addWidget(self._clear_btn)
        zone_layout.addLayout(remove_row)

        controls.addWidget(zone_group)

        # Zone editor (shown when a zone is selected)
        editor_group = QGroupBox("Zone Properties")
        editor_layout = QVBoxLayout(editor_group)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self._zone_name_edit = QLineEdit()
        self._zone_name_edit.setPlaceholderText("e.g. North Approach")
        self._zone_name_edit.textChanged.connect(self._on_zone_name_changed)
        name_row.addWidget(self._zone_name_edit)
        editor_layout.addLayout(name_row)

        approach_row = QHBoxLayout()
        approach_row.addWidget(QLabel("Approach:"))
        self._approach_combo = QComboBox()
        self._approach_combo.addItems([""] + _COMPASS_DIRECTIONS)
        self._approach_combo.currentTextChanged.connect(
            self._on_approach_changed
        )
        approach_row.addWidget(self._approach_combo)
        editor_layout.addLayout(approach_row)

        self._draw_zone_btn = QPushButton("Draw Zone Polygon")
        self._draw_zone_btn.setObjectName("primary_btn")
        self._draw_zone_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._draw_zone_btn.clicked.connect(self._start_drawing)
        editor_layout.addWidget(self._draw_zone_btn)

        self._zone_status = QLabel("Select a zone to edit properties")
        self._zone_status.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px;"
        )
        self._zone_status.setWordWrap(True)
        editor_layout.addWidget(self._zone_status)

        controls.addWidget(editor_group)

        # Navigation
        controls.addStretch()

        nav_row = QHBoxLayout()
        self._back_btn = QPushButton("<  Back")
        self._back_btn.setStyleSheet(BACK_BUTTON_STYLE)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.clicked.connect(self.back_requested.emit)
        nav_row.addWidget(self._back_btn)

        nav_row.addStretch()

        self._continue_btn = QPushButton("Continue  >")
        self._continue_btn.setObjectName("primary_btn")
        self._continue_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._continue_btn.setMinimumWidth(160)
        self._continue_btn.clicked.connect(self._on_continue)
        nav_row.addWidget(self._continue_btn)
        controls.addLayout(nav_row)

        right_panel.setWidget(right_inner)
        layout.addWidget(right_panel, stretch=2)

        # Wire up list selection
        self._zone_list.currentRowChanged.connect(self._on_zone_selected)

    def _load_reference_frame(self) -> None:
        """Load the first frame from the first video."""
        paths = self._video_paths
        if not paths:
            QMessageBox.warning(
                self,
                "No Videos",
                "No video files found. Go back and add videos first.",
            )
            return

        cap = cv2.VideoCapture(paths[0])
        if not cap.isOpened():
            QMessageBox.warning(
                self, "Error", f"Cannot open video: {paths[0]}"
            )
            return

        ret, frame = cap.read()
        cap.release()

        if ret:
            self._preview.set_reference_frame(frame)
            self._zone_status.setText(
                "Reference frame loaded. Add zones and draw polygons."
            )
        else:
            QMessageBox.warning(
                self, "Error", "Could not read first frame from video."
            )

    def _add_zone(self, zone_type: str) -> None:
        """Add a new zone entry to the list."""
        idx = len(self._zones)
        color = _ZONE_COLORS_BGR[idx % len(_ZONE_COLORS_BGR)]
        name = f"Zone {idx + 1}"

        zone = NamedZone(
            name=name,
            zone_type=zone_type,
            polygon=[],
            color_bgr=color,
            approach="",
        )
        self._zones.append(zone)
        self._refresh_zone_list()
        self._zone_list.setCurrentRow(len(self._zones) - 1)

    def _remove_selected_zone(self) -> None:
        """Remove the currently selected zone."""
        row = self._zone_list.currentRow()
        if 0 <= row < len(self._zones):
            self._zones.pop(row)
            self._refresh_zone_list()
            self._preview.set_named_zones(self._zones)

    def _clear_all_zones(self) -> None:
        """Clear all defined zones."""
        if not self._zones:
            return
        reply = QMessageBox.question(
            self,
            "Clear All Zones",
            "Remove all defined zones?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._zones.clear()
            self._refresh_zone_list()
            self._preview.set_named_zones(self._zones)

    def _refresh_zone_list(self) -> None:
        """Refresh the zone list widget from internal state."""
        self._zone_list.clear()
        for zone in self._zones:
            pts = len(zone.polygon)
            approach = f" [{zone.approach}]" if zone.approach else ""
            status = f" ({pts} pts)" if pts >= 3 else " (no polygon)"
            item_text = f"{zone.name} - {zone.zone_type}{approach}{status}"
            item = QListWidgetItem(item_text)
            self._zone_list.addItem(item)

    def _on_zone_selected(self, row: int) -> None:
        """Populate the editor when a zone is selected."""
        if 0 <= row < len(self._zones):
            zone = self._zones[row]
            self._zone_name_edit.blockSignals(True)
            self._zone_name_edit.setText(zone.name)
            self._zone_name_edit.blockSignals(False)

            self._approach_combo.blockSignals(True)
            idx = self._approach_combo.findText(zone.approach)
            self._approach_combo.setCurrentIndex(max(idx, 0))
            self._approach_combo.blockSignals(False)

            pts = len(zone.polygon)
            if pts >= 3:
                self._zone_status.setText(
                    f"Zone has {pts} vertices. Click 'Draw Zone Polygon' to redraw."
                )
            else:
                self._zone_status.setText(
                    "No polygon drawn. Click 'Draw Zone Polygon' to define area."
                )

    def _on_zone_name_changed(self, text: str) -> None:
        """Update zone name when edited."""
        row = self._zone_list.currentRow()
        if 0 <= row < len(self._zones):
            self._zones[row].name = text
            self._refresh_zone_list()
            self._zone_list.setCurrentRow(row)
            self._preview.set_named_zones(self._zones)

    def _on_approach_changed(self, text: str) -> None:
        """Update zone approach direction when changed."""
        row = self._zone_list.currentRow()
        if 0 <= row < len(self._zones):
            self._zones[row].approach = text
            self._refresh_zone_list()
            self._zone_list.setCurrentRow(row)
            self._preview.set_named_zones(self._zones)

    def _start_drawing(self) -> None:
        """Enter polygon drawing mode for the selected zone."""
        row = self._zone_list.currentRow()
        if row < 0 or row >= len(self._zones):
            QMessageBox.information(
                self, "Select Zone", "Select a zone from the list first."
            )
            return

        if self._preview._reference_frame is None:
            QMessageBox.information(
                self,
                "Load Frame",
                "Load a reference frame before drawing zones.",
            )
            return

        self._drawing_zone_index = row
        zone = self._zones[row]
        zone_type = "capture"  # ZoneOverlay uses "capture"/"exclusion"
        self._preview.start_zone_drawing(zone_type)
        self._zone_status.setText(
            f"Drawing: {zone.name} - Click vertices, right-click or click "
            f"near first point to close polygon."
        )

    def _on_polygon_completed(
        self, zone_type: str, points: list[tuple[int, int]]
    ) -> None:
        """Handle completed polygon from the overlay."""
        idx = self._drawing_zone_index
        if 0 <= idx < len(self._zones):
            self._zones[idx].polygon = list(points)
            self._drawing_zone_index = -1
            self._refresh_zone_list()
            self._zone_list.setCurrentRow(idx)
            self._preview.set_named_zones(self._zones)
            self._zone_status.setText(
                f"Polygon set with {len(points)} vertices."
            )

        # Clear the overlay's internal capture zones since we manage
        # zones ourselves via _named_zones
        self._preview._capture_zones.clear()
        self._preview._exclusion_zones.clear()

    def _on_continue(self) -> None:
        """Validate zones and proceed to Step 3."""
        # Validate: need at least 2 zones with polygons
        valid_zones = [z for z in self._zones if len(z.polygon) >= 3]
        if len(valid_zones) < 2:
            QMessageBox.warning(
                self,
                "Insufficient Zones",
                "Define at least 2 zones with drawn polygons to continue.",
            )
            return

        # Validate: all zones should have approach directions
        missing_approach = [z.name for z in valid_zones if not z.approach]
        if missing_approach:
            reply = QMessageBox.question(
                self,
                "Missing Approach Directions",
                f"The following zones have no approach direction set:\n"
                f"{', '.join(missing_approach)}\n\n"
                f"TMC classification requires approach directions. Continue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return

        self.zones_ready.emit(list(self._zones))

    def get_zones(self) -> list[NamedZone]:
        """Return the currently defined zones."""
        return list(self._zones)


# ── Step 3: Processing Page ───────────────────────────────────────────


class _ProcessingPage(QWidget):
    """Processing step with dashboard, live O-D matrix, and TMC summary."""

    back_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._job_config: Optional[JobConfig] = None
        self._zones: list[NamedZone] = []
        self._process_manager: Optional[ProcessManager] = None
        self._monitor_bridge: Optional[MonitorBridge] = None
        self._od_matrix = ODMatrix()
        self._tmc_calculator: Optional[TMCCalculator] = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 16)
        layout.setSpacing(12)

        # Processing dashboard
        self._dashboard = ProcessingDashboard(num_streams=1)
        self._dashboard.start_requested.connect(self._start_processing)
        self._dashboard.stop_requested.connect(self._stop_processing)
        layout.addWidget(self._dashboard)

        # Results area
        results_layout = QHBoxLayout()
        results_layout.setSpacing(12)

        # O-D Matrix table
        od_group = QGroupBox("Origin-Destination Matrix")
        od_layout = QVBoxLayout(od_group)
        self._od_table = QTableWidget()
        self._od_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._od_table.setSortingEnabled(False)
        od_layout.addWidget(self._od_table)

        self._od_total_label = QLabel("Total O-D Pairs: 0")
        self._od_total_label.setStyleSheet(
            f"color: {SUCCESS}; font-size: 13px; font-weight: 600;"
        )
        od_layout.addWidget(self._od_total_label)
        results_layout.addWidget(od_group, stretch=1)

        # TMC Summary table
        tmc_group = QGroupBox("Turning Movement Counts")
        tmc_layout = QVBoxLayout(tmc_group)
        self._tmc_table = QTableWidget()
        self._tmc_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tmc_table.setSortingEnabled(False)
        tmc_layout.addWidget(self._tmc_table)

        self._tmc_total_label = QLabel("")
        self._tmc_total_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px;"
        )
        tmc_layout.addWidget(self._tmc_total_label)
        results_layout.addWidget(tmc_group, stretch=1)

        layout.addLayout(results_layout, stretch=1)

        # Bottom buttons
        btn_row = QHBoxLayout()
        self._back_btn = QPushButton("<  Back")
        self._back_btn.setStyleSheet(BACK_BUTTON_STYLE)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.clicked.connect(self._on_back)
        btn_row.addWidget(self._back_btn)

        btn_row.addStretch()

        self._export_btn = QPushButton("Export to Excel")
        self._export_btn.setObjectName("success_btn")
        self._export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._export_results)
        btn_row.addWidget(self._export_btn)

        layout.addLayout(btn_row)

        # Timer for periodic UI refresh
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(2000)  # 2-second refresh
        self._refresh_timer.timeout.connect(self._refresh_tables)

    def configure(
        self,
        job_config: JobConfig,
        zones: list[NamedZone],
    ) -> None:
        """Set up the processing page with job config and zones."""
        self._job_config = job_config
        self._zones = list(zones)
        self._od_matrix = ODMatrix()

        # Build approach config for TMC
        approach_config = {}
        for zone in zones:
            if zone.approach:
                approach_config[zone.name] = zone.approach
        if approach_config:
            self._tmc_calculator = TMCCalculator(approach_config)
        else:
            self._tmc_calculator = None

        # Initialize tables
        self._init_od_table()
        self._init_tmc_table()

    def _init_od_table(self) -> None:
        """Set up the O-D matrix table with zone headers."""
        zone_names = [z.name for z in self._zones if len(z.polygon) >= 3]
        n = len(zone_names)

        self._od_table.setRowCount(n)
        self._od_table.setColumnCount(n)
        self._od_table.setHorizontalHeaderLabels(zone_names)
        self._od_table.setVerticalHeaderLabels(zone_names)

        if self._od_table.horizontalHeader():
            self._od_table.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeMode.Stretch
            )

        # Initialize all cells to 0
        for r in range(n):
            for c in range(n):
                item = QTableWidgetItem("0")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if r == c:
                    item.setBackground(QColor(BG_SECONDARY))
                self._od_table.setItem(r, c, item)

    def _init_tmc_table(self) -> None:
        """Set up the TMC summary table."""
        if self._tmc_calculator is None:
            self._tmc_table.setRowCount(1)
            self._tmc_table.setColumnCount(1)
            self._tmc_table.setItem(
                0, 0,
                QTableWidgetItem("TMC requires approach directions on zones"),
            )
            return

        approaches = self._tmc_calculator.get_approach_names()
        movements = MOVEMENT_ORDER + ["Total"]

        self._tmc_table.setRowCount(len(approaches))
        self._tmc_table.setColumnCount(len(movements))
        self._tmc_table.setHorizontalHeaderLabels(movements)
        self._tmc_table.setVerticalHeaderLabels(approaches)

        if self._tmc_table.horizontalHeader():
            self._tmc_table.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeMode.Stretch
            )

        for r in range(len(approaches)):
            for c in range(len(movements)):
                item = QTableWidgetItem("0")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._tmc_table.setItem(r, c, item)

    def _start_processing(self) -> None:
        """Start the intersection processing workers."""
        if self._job_config is None:
            return

        self._od_matrix = ODMatrix()
        self._init_od_table()
        self._init_tmc_table()
        self._export_btn.setEnabled(False)

        # Build zone config dicts for the worker
        zone_dicts = []
        for zone in self._zones:
            if len(zone.polygon) >= 3:
                zone_dicts.append({
                    "name": zone.name,
                    "zone_type": zone.zone_type,
                    "polygon": list(zone.polygon),
                    "color_bgr": list(zone.color_bgr),
                    "approach": zone.approach,
                })

        worker_config = {
            "model_path": self._job_config.classification.preset_name
            if hasattr(self._job_config.classification, "preset_name")
            else "yolov8n.pt",
            "zones": zone_dicts,
            "confidence": 0.3,
            "video_start_time": self._job_config.survey_start_time,
        }
        # Always use yolov8n.pt as default model
        worker_config["model_path"] = "yolov8n.pt"

        # Create assignments
        all_paths = self._job_config.all_video_paths
        if not all_paths:
            QMessageBox.warning(
                self, "No Videos", "No video files to process."
            )
            return

        assignments = [
            VideoAssignment(
                stream_id=0,
                video_paths=all_paths,
                use_gpu=True,
                preview_enabled=True,
            )
        ]

        # Set up ProcessManager
        from src.intersection.intersection_subprocess import IntersectionWorker

        self._process_manager = ProcessManager()
        self._process_manager.configure(
            assignments, IntersectionWorker, worker_config
        )
        result_queue = self._process_manager.start()

        # Set up MonitorBridge
        self._monitor_bridge = MonitorBridge(
            result_queue=result_queue,
            expected_streams=1,
        )
        self._monitor_bridge.stream_progress.connect(
            self._dashboard.update_stream_progress
        )
        self._monitor_bridge.stream_status.connect(
            self._dashboard.update_stream_status
        )
        self._monitor_bridge.stream_result.connect(self._on_result)
        self._monitor_bridge.stream_finished.connect(
            self._dashboard.mark_stream_finished
        )
        self._monitor_bridge.stream_error.connect(
            self._dashboard.mark_stream_error
        )
        self._monitor_bridge.all_finished.connect(self._on_all_finished)
        self._monitor_bridge.video_started.connect(
            self._dashboard.update_stream_video
        )
        self._monitor_bridge.start()

        self._dashboard.set_running_state(True)
        self._refresh_timer.start()

    def _stop_processing(self) -> None:
        """Stop all processing workers."""
        self._refresh_timer.stop()

        if self._monitor_bridge is not None:
            self._monitor_bridge.stop()
            self._monitor_bridge.wait(3000)
            self._monitor_bridge = None

        if self._process_manager is not None:
            self._process_manager.stop()
            self._process_manager = None

        self._dashboard.set_running_state(False)
        self._refresh_tables()
        self._export_btn.setEnabled(self._od_matrix.get_total_count() > 0)

    @Slot(int, dict)
    def _on_result(self, stream_id: int, result: dict) -> None:
        """Handle an O-D pair result from the worker."""
        if result.get("type") == "od_pair":
            self._od_matrix.add_od_pair(
                origin=result["origin"],
                dest=result["dest"],
                class_code=result["class"],
                interval_key=result["interval"],
            )

    @Slot(dict)
    def _on_all_finished(self, summary: dict) -> None:
        """All streams completed."""
        self._refresh_timer.stop()
        self._dashboard.mark_all_finished()
        self._refresh_tables()
        self._export_btn.setEnabled(self._od_matrix.get_total_count() > 0)

        if self._monitor_bridge is not None:
            self._monitor_bridge = None
        if self._process_manager is not None:
            self._process_manager = None

    def _refresh_tables(self) -> None:
        """Refresh the O-D matrix and TMC tables from current data."""
        # Update O-D matrix table
        summary = self._od_matrix.get_summary()
        zone_names = [z.name for z in self._zones if len(z.polygon) >= 3]

        for r, origin in enumerate(zone_names):
            for c, dest in enumerate(zone_names):
                count = summary.get(origin, {}).get(dest, 0)
                item = self._od_table.item(r, c)
                if item:
                    item.setText(str(count))
                    if count > 0 and r != c:
                        item.setBackground(QColor(ACCENT_LIGHT))

        total = self._od_matrix.get_total_count()
        self._od_total_label.setText(f"Total O-D Pairs: {total}")

        # Update TMC table
        if self._tmc_calculator is not None:
            tmc_data = self._tmc_calculator.compute_tmc(self._od_matrix)
            total_tmc = self._tmc_calculator.get_total_tmc(self._od_matrix)
            approaches = self._tmc_calculator.get_approach_names()

            for r, approach in enumerate(approaches):
                approach_data = total_tmc.get(approach, {})
                row_total = 0
                for c, movement in enumerate(MOVEMENT_ORDER):
                    classes = approach_data.get(movement, {})
                    count = sum(classes.values())
                    row_total += count
                    item = self._tmc_table.item(r, c)
                    if item:
                        item.setText(str(count))

                # Total column
                total_item = self._tmc_table.item(r, len(MOVEMENT_ORDER))
                if total_item:
                    total_item.setText(str(row_total))

            movement_totals = self._tmc_calculator.get_movement_totals(
                tmc_data
            )
            parts = [f"{k}: {v}" for k, v in movement_totals.items()]
            self._tmc_total_label.setText("  |  ".join(parts))

    def _on_back(self) -> None:
        """Handle back button."""
        self._stop_processing()
        self.back_requested.emit()

    def _export_results(self) -> None:
        """Export results to Excel."""
        if self._job_config is None:
            return

        job_num = self._job_config.job_number or "Intersection"
        default_name = f"TMC_Report_{job_num}.xlsx"
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Save TMC Report",
            default_name,
            "Excel Files (*.xlsx)",
        )
        if not filepath:
            return

        tmc_data = {}
        if self._tmc_calculator is not None:
            tmc_data = self._tmc_calculator.compute_tmc(self._od_matrix)

        exporter = IntersectionExporter()
        exporter.export_tmc(
            filepath=filepath,
            job_config=self._job_config,
            tmc_data=tmc_data,
            od_matrix=self._od_matrix,
        )
        QMessageBox.information(
            self, "Export Complete", f"Report saved to:\n{filepath}"
        )


# ── Main Intersection Page ────────────────────────────────────────────


class _IntersectionFolderPage(QWidget):
    """Step 1: Job folder selection for Intersection counting."""

    folder_ready = Signal(dict)  # scan result dict
    quick_start = Signal()  # skip folder scanning
    back_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        from src.common.job_folder_widget import JobFolderWidget
        from src.common.theme import NAVY, NAVY_LIGHT

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 20)
        layout.setSpacing(12)

        # Back button
        back_row = QHBoxLayout()
        back_btn = QPushButton("<  Back to Menu")
        back_btn.setStyleSheet(BACK_BUTTON_STYLE)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self.back_requested.emit)
        back_row.addWidget(back_btn)
        back_row.addStretch()
        layout.addLayout(back_row)

        # Title
        title = QLabel("Intersection Counter — Select Job Folder")
        title.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 20px; font-weight: 700; padding: 4px 0;"
        )
        layout.addWidget(title)

        # Quick Start option — skip folder scanning
        quick_row = QHBoxLayout()
        quick_label = QLabel("Or skip folder scanning and add individual videos:")
        quick_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        quick_row.addWidget(quick_label)

        quick_btn = QPushButton("Quick Start — Single Videos")
        quick_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        quick_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {NAVY_LIGHT};
                border: 1.5px solid {NAVY};
                border-radius: 6px;
                color: {NAVY};
                font-size: 12px;
                font-weight: 600;
                padding: 8px 20px;
            }}
            QPushButton:hover {{
                background-color: {NAVY};
                color: white;
            }}
        """)
        quick_btn.clicked.connect(self.quick_start.emit)
        quick_row.addWidget(quick_btn)
        quick_row.addStretch()
        layout.addLayout(quick_row)

        layout.addSpacing(8)

        self.job_folder_widget = JobFolderWidget()
        self.job_folder_widget.videos_selected.connect(self._on_videos_confirmed)
        layout.addWidget(self.job_folder_widget)

        layout.addStretch()

    def _on_videos_confirmed(self, video_paths: list) -> None:
        info = self.job_folder_widget.get_job_info()
        info["selected_videos"] = video_paths
        self.folder_ready.emit(info)


class IntersectionPage(QWidget):
    """3-step wizard for Intersection Turning Movement Counting.

    Step 1: Folder Selection
    Step 2: Zone Definition
    Step 3: Processing & Results
    """

    back_to_menu = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._job_config: Optional[JobConfig] = None
        self._scan_result: dict = {}
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Step indicators ──
        step_bar = QFrame()
        step_bar.setStyleSheet(
            f"QFrame {{ background-color: {BG_PRIMARY}; "
            f"border-bottom: 1px solid {BORDER}; }}"
        )
        step_layout = QHBoxLayout(step_bar)
        step_layout.setContentsMargins(24, 12, 24, 12)

        self._step_labels: list[QLabel] = []
        step_names = [
            "1. Folder Selection",
            "2. Zone Definition",
            "3. Processing",
        ]
        for i, name in enumerate(step_names):
            lbl = QLabel(name)
            if i == 0:
                lbl.setStyleSheet(STEP_ACTIVE)
            else:
                lbl.setStyleSheet(STEP_INACTIVE)
            self._step_labels.append(lbl)
            step_layout.addWidget(lbl)

            if i < len(step_names) - 1:
                separator = QLabel("  >  ")
                separator.setStyleSheet(f"color: {TEXT_MUTED};")
                step_layout.addWidget(separator)

        step_layout.addStretch()
        layout.addWidget(step_bar)

        # ── Stacked pages ──
        self._stack = QStackedWidget()

        # Step 1: Folder Selection
        self._step1 = _IntersectionFolderPage()
        self._step1.folder_ready.connect(self._on_step1_continue)
        self._step1.quick_start.connect(self._on_quick_start)
        self._step1.back_requested.connect(self.back_to_menu.emit)
        self._stack.addWidget(self._step1)

        # Step 2: Zone Definition
        self._step2 = _ZoneDefinitionPage()
        self._step2.zones_ready.connect(self._on_step2_continue)
        self._step2.back_requested.connect(lambda: self._go_to_step(0))
        self._stack.addWidget(self._step2)

        # Step 3: Processing
        self._step3 = _ProcessingPage()
        self._step3.back_requested.connect(lambda: self._go_to_step(1))
        self._stack.addWidget(self._step3)

        layout.addWidget(self._stack, stretch=1)

    def _go_to_step(self, step: int) -> None:
        """Navigate to a specific step."""
        self._stack.setCurrentIndex(step)

        # Update step indicators
        for i, lbl in enumerate(self._step_labels):
            if i < step:
                lbl.setStyleSheet(STEP_COMPLETED)
            elif i == step:
                lbl.setStyleSheet(STEP_ACTIVE)
            else:
                lbl.setStyleSheet(STEP_INACTIVE)

    def _on_quick_start(self) -> None:
        """Skip folder scanning — go directly to zone definition."""
        self._scan_result = {}
        self._job_config = JobConfig(
            job_number="",
            job_name="",
            module_type="intersection",
            job_folder_path="",
        )
        self._step2.set_video_paths([])
        self._go_to_step(1)

    @Slot(dict)
    def _on_step1_continue(self, scan_result: dict) -> None:
        """Folder selection complete — build config and move to zone definition."""
        self._scan_result = scan_result
        selected_videos = scan_result.get("selected_videos", [])

        # Build a JobConfig from scan data
        from src.common.data_models import SiteConfig
        self._job_config = JobConfig(
            job_number=scan_result.get("job_number", ""),
            job_name=scan_result.get("job_name", ""),
            module_type="intersection",
            job_folder_path=scan_result.get("job_folder_path", ""),
        )
        # Populate video paths into the job config sites
        sites_summary = scan_result.get("sites_summary", [])
        if sites_summary:
            for site_info in sites_summary:
                site_videos = [
                    vp for s in scan_result.get("sites", [])
                    if s["site_name"] == site_info["site_name"]
                    for vp in s.get("video_paths", [])
                    if vp in selected_videos
                ]
                self._job_config.sites.append(SiteConfig(
                    site_number=site_info.get("site_id", ""),
                    site_name=site_info.get("site_name", ""),
                    direction=site_info.get("direction", ""),
                    video_paths=site_videos,
                ))
        elif selected_videos:
            self._job_config.sites.append(SiteConfig(
                video_paths=selected_videos,
            ))

        self._step2.set_video_paths(selected_videos)
        self._go_to_step(1)

    @Slot(list)
    def _on_step2_continue(self, zones: list[NamedZone]) -> None:
        """Step 2 complete - move to processing."""
        if self._job_config is None:
            return
        self._step3.configure(self._job_config, zones)
        self._go_to_step(2)
