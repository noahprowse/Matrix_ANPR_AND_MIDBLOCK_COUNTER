"""Pedestrian Counter module UI page — 3-step wizard.

Step 1: Folder Selection or Quick Start (single videos)
Step 2: Video & Line Setup (videos, count lines, zones)
Step 3: Processing (multi-process with ProcessingDashboard, results table, export)
"""

import os
from collections import defaultdict

import cv2
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QFileDialog,
    QGroupBox,
    QComboBox,
    QHeaderView,
    QSizePolicy,
    QScrollArea,
    QMessageBox,
    QStackedWidget,
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont, QImage, QPixmap

from src.common.theme import (
    ACCENT,
    BORDER,
    NAVY,
    NAVY_LIGHT,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_MUTED,
    SUCCESS,
    BACK_BUTTON_STYLE,
)
from src.common.data_models import JobConfig, VideoAssignment
from src.common.video_list_widget import VideoListWidget
from src.common.time_filter_widget import TimeFilterWidget
from src.common.zone_widget import ZoneControlWidget
from src.common.survey_widget import SurveyInfo
from src.common.clickable_preview import ClickablePreview, StepIndicator
from src.pedestrian.pedestrian_export import export_pedestrian_results
from src.engine.process_manager import ProcessManager, create_chunked_assignments
from src.engine.monitor_bridge import MonitorBridge
from src.engine.processing_dashboard import ProcessingDashboard

_MAX_WORKERS = min(4, (os.cpu_count() or 4) // 2)


class PedestrianPage(QWidget):
    """Pedestrian Counter page — 3-step wizard.

    Page 0: Folder Selection (JobFolderWidget) or Quick Start
    Page 1: Video & Line Setup
    Page 2: Processing (multi-process)
    """

    def __init__(self, on_back=None, parent=None):
        super().__init__(parent)
        self._on_back = on_back
        self._results = None
        self._job_config: JobConfig | None = None
        self._scan_result: dict = {}
        self._process_manager: ProcessManager | None = None
        self._monitor_bridge: MonitorBridge | None = None
        self._accumulated_results: dict = {}
        self._build_ui()

    # ================================================================
    # UI construction
    # ================================================================

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._step_indicator = StepIndicator(
            ["Step 1: Folder Selection", "Step 2: Setup & Config", "Step 3: Processing"]
        )
        root.addWidget(self._step_indicator)

        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)

        self._build_step1()
        self._build_step2()
        self._build_step3()

    # ------------------------------------------------------------------
    # Step 1 — Folder Selection
    # ------------------------------------------------------------------

    def _build_step1(self):
        from src.common.job_folder_widget import JobFolderWidget

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 10, 20, 20)
        layout.setSpacing(12)

        back_row = QHBoxLayout()
        back_btn = QPushButton("<  Back to Menu")
        back_btn.setStyleSheet(BACK_BUTTON_STYLE)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self._go_back)
        back_row.addWidget(back_btn)
        back_row.addStretch()
        layout.addLayout(back_row)

        title = QLabel("Pedestrian Counter — Select Job Folder")
        title.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 20px; font-weight: 700; padding: 4px 0;"
        )
        layout.addWidget(title)

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
        quick_btn.clicked.connect(self._on_quick_start)
        quick_row.addWidget(quick_btn)
        quick_row.addStretch()
        layout.addLayout(quick_row)

        layout.addSpacing(8)

        self._folder_widget = JobFolderWidget()
        self._folder_widget.videos_selected.connect(self._on_folder_videos_confirmed)
        layout.addWidget(self._folder_widget)

        layout.addStretch()
        self._stack.addWidget(page)

    # ------------------------------------------------------------------
    # Step 2 — Video & Line Setup
    # ------------------------------------------------------------------

    def _build_step2(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 10, 20, 20)
        layout.setSpacing(12)

        top_bar = QHBoxLayout()
        back_btn = QPushButton("<  Back")
        back_btn.setStyleSheet(BACK_BUTTON_STYLE)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self._go_to_step1)
        top_bar.addWidget(back_btn)

        title = QLabel("Video & Line Setup")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {ACCENT};")
        top_bar.addWidget(title)
        top_bar.addStretch()

        self._step2_next_btn = QPushButton("Start Processing  >")
        self._step2_next_btn.setObjectName("primary_btn")
        self._step2_next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._step2_next_btn.setEnabled(False)
        self._step2_next_btn.clicked.connect(self._on_step2_continue)
        top_bar.addWidget(self._step2_next_btn)
        layout.addLayout(top_bar)

        content = QHBoxLayout()
        content.setSpacing(16)

        self.video_preview = ClickablePreview()
        self.video_preview.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.video_preview.line_added.connect(self._on_line_added)
        self.video_preview.zone_completed.connect(self._on_zone_completed)
        content.addWidget(self.video_preview, stretch=3)

        controls_scroll = QScrollArea()
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        controls_inner = QWidget()
        controls = QVBoxLayout(controls_inner)
        controls.setSpacing(10)

        self.video_list = VideoListWidget()
        self.video_list.overlay_detected.connect(self._on_overlay_detected)
        self.video_list.first_frame_ready.connect(self._on_first_frame)
        self.video_list.videos_changed.connect(self._on_videos_changed)
        controls.addWidget(self.video_list)

        self.time_filter = TimeFilterWidget()
        controls.addWidget(self.time_filter)

        line_group = QGroupBox("Count Lines")
        line_layout = QVBoxLayout(line_group)

        add_line_row = QHBoxLayout()
        self.direction_combo = QComboBox()
        self.direction_combo.addItems(["NB", "SB", "EB", "WB"])
        self.direction_combo.setFixedWidth(70)
        add_line_row.addWidget(QLabel("Dir:"))
        add_line_row.addWidget(self.direction_combo)

        self.lane_input = QLineEdit()
        self.lane_input.setPlaceholderText("Lane #")
        self.lane_input.setFixedWidth(70)
        self.lane_input.setText("1")
        self.lane_input.setMaxLength(3)
        add_line_row.addWidget(QLabel("Lane:"))
        add_line_row.addWidget(self.lane_input)

        self.add_line_btn = QPushButton("Add Line")
        self.add_line_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_line_btn.clicked.connect(self._start_add_line)
        add_line_row.addWidget(self.add_line_btn)
        line_layout.addLayout(add_line_row)

        self.lines_list = QLabel("No count lines defined")
        self.lines_list.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self.lines_list.setWordWrap(True)
        line_layout.addWidget(self.lines_list)

        line_btns = QHBoxLayout()
        undo_btn = QPushButton("Remove Last")
        undo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        undo_btn.clicked.connect(self._remove_last_line)
        line_btns.addWidget(undo_btn)
        clear_btn = QPushButton("Clear All Lines")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.clicked.connect(self._clear_all_lines)
        line_btns.addWidget(clear_btn)
        line_layout.addLayout(line_btns)
        controls.addWidget(line_group)

        self.zone_widget = ZoneControlWidget()
        self.zone_widget.zone_draw_requested.connect(
            lambda zt: self.video_preview.start_zone_drawing(zt)
        )
        controls.addWidget(self.zone_widget)
        controls.addStretch()

        controls_scroll.setWidget(controls_inner)
        content.addWidget(controls_scroll, stretch=2)
        layout.addLayout(content)

        self.step2_status = QLabel("Load videos and draw count lines to continue")
        self.step2_status.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        layout.addWidget(self.step2_status)

        self._stack.addWidget(page)

    # ------------------------------------------------------------------
    # Step 3 — Processing (multi-process)
    # ------------------------------------------------------------------

    def _build_step3(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 10, 20, 20)
        layout.setSpacing(12)

        top_bar = QHBoxLayout()
        self._step3_back_btn = QPushButton("<  Back to Setup")
        self._step3_back_btn.setStyleSheet(BACK_BUTTON_STYLE)
        self._step3_back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._step3_back_btn.clicked.connect(self._go_to_step2_from_step3)
        top_bar.addWidget(self._step3_back_btn)

        title = QLabel("Processing")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {ACCENT};")
        top_bar.addWidget(title)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        # Processing dashboard (multi-stream progress cards)
        self._dashboard = ProcessingDashboard(num_streams=_MAX_WORKERS)
        self._dashboard.start_requested.connect(self._start_processing)
        self._dashboard.stop_requested.connect(self._stop_processing)
        layout.addWidget(self._dashboard)

        # Results table
        results_group = QGroupBox("Pedestrian Counts")
        results_layout = QVBoxLayout(results_group)

        self.results_table = QTableWidget()
        self.results_table.setColumnCount(3)
        self.results_table.setHorizontalHeaderLabels(["Line", "Direction", "Count"])
        self.results_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.setSortingEnabled(True)
        results_layout.addWidget(self.results_table)

        self.total_label = QLabel("Total: 0")
        self.total_label.setStyleSheet(
            f"color: {SUCCESS}; font-size: 14px; font-weight: bold;"
        )
        results_layout.addWidget(self.total_label)
        layout.addWidget(results_group, stretch=1)

        self.export_btn = QPushButton("Export to Excel")
        self.export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._export_results)
        layout.addWidget(self.export_btn)

        self._stack.addWidget(page)

    # ================================================================
    # Navigation
    # ================================================================

    def _set_step(self, index: int):
        self._stack.setCurrentIndex(index)
        self._step_indicator.set_current(index)

    def _go_back(self):
        self._stop_processing()
        if self._on_back:
            self._on_back()

    def _go_to_step1(self):
        self._set_step(0)

    def _go_to_step2_from_step3(self):
        if self._process_manager and self._process_manager.is_running:
            reply = QMessageBox.question(
                self, "Processing in Progress",
                "Stop processing and go back to setup?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self._stop_processing()
        self._set_step(1)

    def _on_quick_start(self):
        self._scan_result = {}
        self._set_step(1)

    def _on_folder_videos_confirmed(self, video_paths: list):
        self._scan_result = self._folder_widget.get_job_info()
        self._scan_result["selected_videos"] = video_paths
        selected = self._scan_result.get("selected_videos", [])
        if selected:
            self.video_list.add_videos(selected)
        self._set_step(1)

    def _on_step2_continue(self):
        if self._job_config is None and self._scan_result:
            self._job_config = JobConfig(
                job_number=self._scan_result.get("job_number", ""),
                job_name=self._scan_result.get("job_name", ""),
                module_type="pedestrian",
                job_folder_path=self._scan_result.get("job_folder_path", ""),
            )
        elif self._job_config is None:
            self._job_config = JobConfig(
                job_number="", job_name="", module_type="pedestrian", job_folder_path="",
            )
        self._set_step(2)
        self._start_processing()

    # ================================================================
    # Step 2 signal handlers
    # ================================================================

    def _on_overlay_detected(self, overlay: dict):
        if overlay.get("timestamp"):
            self.time_filter.set_times(overlay["timestamp"], None)
        self.step2_status.setText(
            f"Auto-detected: Camera {overlay.get('camera_number', '?')}, "
            f"Time {overlay.get('timestamp', '?')}"
        )

    def _on_first_frame(self, frame):
        self.video_preview.set_frame(frame)
        self.step2_status.setText("Video loaded -- add count lines, then start processing")

    def _on_videos_changed(self, paths: list):
        self._update_step2_next_button()

    # ================================================================
    # Line management
    # ================================================================

    def _start_add_line(self):
        if self._first_frame_loaded():
            direction = self.direction_combo.currentText()
            lane = self.lane_input.text().strip() or "1"
            label = f"{direction} Lane {lane}"
            self.video_preview.start_drawing(label)
            self.step2_status.setText(f"Click two points on the video for: {label}")

    def _on_line_added(self, line: dict):
        self._refresh_lines_list()
        self._update_step2_next_button()
        try:
            current_lane = int(self.lane_input.text().strip())
            self.lane_input.setText(str(current_lane + 1))
        except ValueError:
            pass
        self.step2_status.setText(f"Line added: {line['label']}")

    def _remove_last_line(self):
        self.video_preview.remove_last_line()
        self._refresh_lines_list()
        self._update_step2_next_button()

    def _clear_all_lines(self):
        if not self.video_preview.get_lines():
            return
        reply = QMessageBox.question(
            self, "Clear All Lines", "Remove all count lines?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.video_preview.clear_all_lines()
            self._refresh_lines_list()
            self._update_step2_next_button()

    def _refresh_lines_list(self):
        lines = self.video_preview.get_lines()
        if not lines:
            self.lines_list.setText("No count lines defined")
            self.lines_list.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        else:
            text = "\n".join(f"  {i+1}. {ln['label']}" for i, ln in enumerate(lines))
            self.lines_list.setText(text)
            self.lines_list.setStyleSheet(f"color: {SUCCESS}; font-size: 11px;")

    def _on_zone_completed(self, zone_type: str, points: list):
        self.zone_widget.add_zone(zone_type, points)
        self.video_preview._redraw()

    def _first_frame_loaded(self) -> bool:
        return self.video_preview._first_frame is not None

    def _update_step2_next_button(self):
        has_videos = len(self.video_list.get_video_paths()) > 0
        has_lines = len(self.video_preview.get_lines()) > 0
        self._step2_next_btn.setEnabled(has_videos and has_lines)

    # ================================================================
    # Processing (Step 3) — Multi-process via ProcessManager
    # ================================================================

    def _init_accumulated_results(self):
        lines = self.video_preview.get_lines()
        per_line_counts = {}
        per_line_intervals = {}
        for line in lines:
            label = line["label"]
            per_line_counts[label] = {"in": 0, "out": 0}
            per_line_intervals[label] = defaultdict(lambda: {"in": 0, "out": 0})
        self._accumulated_results = {
            "per_line_counts": per_line_counts,
            "per_line_intervals": per_line_intervals,
            "grand_total": 0,
        }

    def _start_processing(self):
        paths = self.video_list.get_video_paths()
        lines = self.video_preview.get_lines()
        if not paths or not lines:
            return

        self._results = None
        self.results_table.setSortingEnabled(False)
        self.results_table.setRowCount(0)
        self.total_label.setText("Total: 0")
        self.export_btn.setEnabled(False)
        self._step3_back_btn.setEnabled(False)

        self._init_accumulated_results()

        serialized_lines = []
        for line in lines:
            serialized_lines.append({
                "start": tuple(line["start"]),
                "end": tuple(line["end"]),
                "label": line["label"],
                "color_bgr": tuple(line["color_bgr"]),
            })

        overlay = self.video_list.get_overlay_result()
        video_start_time = overlay.get("timestamp", "") if overlay else ""

        worker_config = {
            "model_path": "yolo11x.pt",
            "count_lines": serialized_lines,
            "confidence": 0.3,
            "video_start_time": video_start_time,
            "capture_zones": self.zone_widget.capture_zones,
            "exclusion_zones": self.zone_widget.exclusion_zones,
        }

        assignments = create_chunked_assignments(
            video_paths=paths,
            max_workers=_MAX_WORKERS,
            chunk_duration_minutes=15.0,
        )
        if not assignments:
            QMessageBox.warning(self, "No Videos", "No processable video files found.")
            self._step3_back_btn.setEnabled(True)
            return

        for a in assignments:
            a.use_gpu = True
            a.preview_enabled = True

        from src.pedestrian.pedestrian_subprocess import PedestrianSubprocessWorker

        self._process_manager = ProcessManager()
        self._process_manager.configure(
            assignments, PedestrianSubprocessWorker, worker_config,
        )
        result_queue = self._process_manager.start()

        self._monitor_bridge = MonitorBridge(
            result_queue=result_queue,
            expected_streams=len(assignments),
        )
        self._monitor_bridge.stream_progress.connect(self._dashboard.update_stream_progress)
        self._monitor_bridge.stream_status.connect(self._dashboard.update_stream_status)
        self._monitor_bridge.stream_result.connect(self._on_result)
        self._monitor_bridge.stream_finished.connect(self._dashboard.mark_stream_finished)
        self._monitor_bridge.stream_error.connect(self._dashboard.mark_stream_error)
        self._monitor_bridge.all_finished.connect(self._on_all_finished)
        self._monitor_bridge.video_started.connect(self._dashboard.update_stream_video)
        self._monitor_bridge.start()

        self._dashboard.set_running_state(True)

    def _stop_processing(self):
        if self._monitor_bridge is not None:
            self._monitor_bridge.stop()
            self._monitor_bridge.wait(3000)
            self._monitor_bridge = None

        if self._process_manager is not None:
            self._process_manager.stop()
            self._process_manager = None

        self._dashboard.set_running_state(False)
        self._step3_back_btn.setEnabled(True)

    @Slot(int, dict)
    def _on_result(self, stream_id: int, result: dict):
        if result.get("type") != "ped_crossing":
            return

        label = result["line_label"]
        direction = result["direction"]

        acc = self._accumulated_results
        if label in acc["per_line_counts"]:
            acc["per_line_counts"][label][direction] += 1
            interval = result.get("interval_key", "")
            if interval:
                acc["per_line_intervals"][label][interval][direction] += 1
            acc["grand_total"] += 1

        self.total_label.setText(f"Total: {acc['grand_total']}")

    @Slot(dict)
    def _on_all_finished(self, summary: dict):
        self._dashboard.mark_all_finished()
        self._step3_back_btn.setEnabled(True)

        if self._monitor_bridge is not None:
            self._monitor_bridge = None
        if self._process_manager is not None:
            self._process_manager = None

        acc = self._accumulated_results
        lines = self.video_preview.get_lines()
        per_line = {}
        grand_total = 0

        for line in lines:
            label = line["label"]
            counts = acc["per_line_counts"].get(label, {"in": 0, "out": 0})
            count_in = counts["in"]
            count_out = counts["out"]
            line_total = count_in + count_out
            grand_total += line_total

            per_line[label] = {
                "count_in": count_in,
                "count_out": count_out,
                "total": line_total,
                "intervals": {
                    k: dict(v) for k, v in sorted(
                        acc["per_line_intervals"].get(label, {}).items()
                    )
                },
            }

        self._results = {
            "per_line": per_line,
            "grand_total": grand_total,
            "line_labels": [line["label"] for line in lines],
            "video_count": len(self.video_list.get_video_paths()),
        }

        self._populate_results_table(self._results)
        self.results_table.setSortingEnabled(True)
        self.export_btn.setEnabled(True)

    def _populate_results_table(self, results: dict):
        per_line = results.get("per_line", {})
        self.results_table.setRowCount(0)

        grand_total = 0
        for line_label, line_data in per_line.items():
            count_in = line_data.get("count_in", 0)
            count_out = line_data.get("count_out", 0)

            for direction, count in [("IN", count_in), ("OUT", count_out)]:
                if count == 0:
                    continue
                grand_total += count
                row = self.results_table.rowCount()
                self.results_table.insertRow(row)
                self.results_table.setItem(row, 0, QTableWidgetItem(line_label))
                self.results_table.setItem(row, 1, QTableWidgetItem(direction))
                self.results_table.setItem(row, 2, QTableWidgetItem(str(count)))

        self.total_label.setText(f"Total: {grand_total}")

    def _export_results(self):
        if not self._results:
            return
        job = self._job_config
        survey = SurveyInfo(
            job_number=job.job_number if job else "",
            job_name=job.job_name if job else "",
            site_number=job.sites[0].site_number if job and job.sites else "",
            site_name=job.sites[0].site_name if job and job.sites else "",
            camera_number="",
        )
        site = survey.site_number or (job.job_number if job else "Unknown")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Excel Report",
            f"Pedestrian_Report_{site}.xlsx",
            "Excel Files (*.xlsx)",
        )
        if path:
            export_pedestrian_results(self._results, survey, path)
