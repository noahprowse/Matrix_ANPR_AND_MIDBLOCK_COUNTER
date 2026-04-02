"""ANPR Data Extraction module UI page with 4-step wizard flow.

Step 1 (Folder Selection): Job folder scanning and video discovery.
Step 2 (Setup & Config): Direction of travel, zones, Claude, blob storage.
Step 3 (Processing): Parallel video processing with vehicle tracking + results.
Step 4 (QA Review): Vehicle card review, corrections, AI validation, export.
"""

import os
import re
import time

import cv2
import numpy as np

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QFileDialog,
    QGroupBox,
    QHeaderView,
    QSizePolicy,
    QScrollArea,
    QComboBox,
    QCheckBox,
    QLineEdit,
    QDoubleSpinBox,
    QStackedWidget,
    QSlider,
    QSpinBox,
    QGridLayout,
    QFrame,
)
from PySide6.QtCore import Qt, Slot, Signal, QTimer
from PySide6.QtGui import QImage, QPixmap

from src.common.theme import (
    TEXT_SECONDARY,
    TEXT_MUTED,
    SUCCESS,
    WARNING,
    DANGER,
    BORDER,
    BG_SECONDARY,
    NAVY,
    NAVY_LIGHT,
    STEP_ACTIVE,
    STEP_INACTIVE,
    STEP_COMPLETED,
    BACK_BUTTON_STYLE,
)
from src.common.job_details_widget import JobDetailsWidget
from src.common.data_models import JobConfig
from src.common.job_folder_widget import JobFolderWidget
from src.common.zone_widget import ZoneOverlay, ZoneControlWidget
from src.common.blob_storage import BlobStorageWidget
from src.anpr.anpr_worker import ANPRWorker
from src.anpr.anpr_export import export_anpr_results
from src.anpr.claude_validator import ClaudePlateValidator
from src.anpr.qa_review_page import ANPRQAReviewPage


# ── ANPRPreview: video preview with zone overlay support ─────────────


class ANPRPreview(ZoneOverlay, QLabel):
    """Video preview label with zone drawing support for ANPR.

    Combines QLabel display with the ZoneOverlay mixin so users can draw
    capture and exclusion zones directly on the video preview.
    """

    zone_completed = Signal(str, list)  # (zone_type, [(x,y), ...])

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(640, 360)
        self.setStyleSheet("background-color: #F1F3F5; border-radius: 8px;")
        self.setText("No video loaded")

        self._video_size: tuple[int, int] | None = None
        self.zone_overlay_init()

    def update_frame(self, frame: np.ndarray):
        """Update display with a BGR OpenCV frame and store frame dimensions."""
        h, w = frame.shape[:2]
        self._video_size = (w, h)
        self.set_frame_size(w, h)

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        bytes_per_line = 3 * w
        qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)
        scaled = pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)

    def widget_to_video(self, wx: float, wy: float) -> tuple[int, int] | None:
        """Map widget coordinates to video frame coordinates."""
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
        vx = int(px * vw / pw)
        vy = int(py * vh / ph)
        return (vx, vy)

    def clear_frame(self):
        """Reset to placeholder text."""
        self.clear()
        self.setText("No video loaded")


# ── Step indicator widget ─────────────────────────────────────────────


class _StepIndicator(QWidget):
    """Horizontal step indicator: Step 1 . Step 2 . Step 3."""

    def __init__(self, labels: list[str], parent=None):
        super().__init__(parent)
        self._labels = labels
        self._step_labels: list[QLabel] = []
        self._dot_labels: list[QLabel] = []
        self._build_ui()
        self.set_active(0)

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 8, 20, 8)
        layout.setSpacing(0)
        layout.addStretch()

        for i, text in enumerate(self._labels):
            lbl = QLabel(f"Step {i + 1}: {text}")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._step_labels.append(lbl)
            layout.addWidget(lbl)

            if i < len(self._labels) - 1:
                dot = QLabel("  \u2022  ")
                dot.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 14px;")
                dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self._dot_labels.append(dot)
                layout.addWidget(dot)

        layout.addStretch()

    def set_active(self, step: int):
        """Highlight the given step (0-indexed) as active."""
        for i, lbl in enumerate(self._step_labels):
            if i < step:
                lbl.setStyleSheet(STEP_COMPLETED)
            elif i == step:
                lbl.setStyleSheet(STEP_ACTIVE)
            else:
                lbl.setStyleSheet(STEP_INACTIVE)


# ── Step 2: Folder Upload & Config Page ──────────────────────────────


class ANPRSetupPage(QWidget):
    """Step 2: Folder upload, direction of travel, zones, Claude, blob."""

    continue_clicked = Signal()
    back_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._video_paths: list[str] = []
        self._reference_frame: np.ndarray | None = None
        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Back button ───────────────────────────────────────────────
        back_row = QHBoxLayout()
        back_row.setContentsMargins(20, 6, 20, 0)
        back_btn = QPushButton("<  Back to Job Details")
        back_btn.setStyleSheet(BACK_BUTTON_STYLE)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self.back_clicked.emit)
        back_row.addWidget(back_btn)
        back_row.addStretch()
        outer.addLayout(back_row)

        # ── Main 2-column layout ─────────────────────────────────────
        content = QHBoxLayout()
        content.setSpacing(16)
        content.setContentsMargins(20, 10, 20, 20)

        # Left: ANPRPreview for zone drawing
        left = QVBoxLayout()
        left.setSpacing(8)

        self.video_preview = ANPRPreview()
        self.video_preview.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        left.addWidget(self.video_preview, stretch=1)

        # Video scrubber: slider + frame info
        scrubber_row = QHBoxLayout()
        scrubber_row.setSpacing(8)

        self._frame_label = QLabel("No video loaded")
        self._frame_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        self._frame_label.setMinimumWidth(160)

        self._scrubber = QSlider(Qt.Orientation.Horizontal)
        self._scrubber.setMinimum(0)
        self._scrubber.setMaximum(0)
        self._scrubber.setEnabled(False)
        self._scrubber.valueChanged.connect(self._on_scrubber_changed)
        self._scrubber.setStyleSheet(
            "QSlider::groove:horizontal { height: 6px; background: #D1D5DB; border-radius: 3px; }"
            "QSlider::handle:horizontal { width: 14px; margin: -4px 0; background: #1B2A4A; border-radius: 7px; }"
            "QSlider::sub-page:horizontal { background: #1B2A4A; border-radius: 3px; }"
        )

        # Video selector combo for multi-video scrubbing
        self._video_combo = QComboBox()
        self._video_combo.setMinimumWidth(120)
        self._video_combo.setMaximumWidth(200)
        self._video_combo.currentIndexChanged.connect(self._on_video_combo_changed)

        scrubber_row.addWidget(self._video_combo)
        scrubber_row.addWidget(self._scrubber, stretch=1)
        scrubber_row.addWidget(self._frame_label)

        left.addLayout(scrubber_row)

        # Load Reference Frame button (kept as fallback)
        self.load_frame_btn = QPushButton("Load Reference Frame")
        self.load_frame_btn.setObjectName("primary_btn")
        self.load_frame_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.load_frame_btn.setEnabled(False)
        self.load_frame_btn.clicked.connect(self._load_reference_frame)
        left.addWidget(self.load_frame_btn)

        content.addLayout(left, stretch=3)

        # Right: controls in scroll area
        controls_scroll = QScrollArea()
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        controls_inner = QWidget()
        controls = QVBoxLayout(controls_inner)
        controls.setSpacing(10)

        # 1. Job Folder Widget
        self.job_folder_widget = JobFolderWidget()
        controls.addWidget(self.job_folder_widget)

        # 2. Video discovery summary
        self.video_summary_label = QLabel("No videos discovered yet.")
        self.video_summary_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 12px;"
        )
        self.video_summary_label.setWordWrap(True)
        controls.addWidget(self.video_summary_label)

        # 3. Direction of Travel
        direction_group = QGroupBox("Direction of Travel")
        direction_layout = QVBoxLayout(direction_group)
        direction_layout.setSpacing(6)

        towards_row = QHBoxLayout()
        towards_lbl = QLabel("Towards Camera:")
        towards_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        towards_row.addWidget(towards_lbl)
        self.towards_combo = QComboBox()
        self.towards_combo.addItems(["NB", "SB", "EB", "WB"])
        self.towards_combo.setCurrentIndex(0)
        towards_row.addWidget(self.towards_combo)
        direction_layout.addLayout(towards_row)

        away_row = QHBoxLayout()
        away_lbl = QLabel("Away from Camera:")
        away_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        away_row.addWidget(away_lbl)
        self.away_combo = QComboBox()
        self.away_combo.addItems(["NB", "SB", "EB", "WB"])
        self.away_combo.setCurrentIndex(1)
        away_row.addWidget(self.away_combo)
        direction_layout.addLayout(away_row)

        controls.addWidget(direction_group)

        # 3b. Parallel Processing
        parallel_group = QGroupBox("Parallel Processing")
        parallel_layout = QHBoxLayout(parallel_group)
        parallel_layout.setSpacing(8)

        workers_lbl = QLabel("Workers:")
        workers_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        parallel_layout.addWidget(workers_lbl)

        self.worker_count_spin = QSpinBox()
        self.worker_count_spin.setRange(1, 8)
        self.worker_count_spin.setValue(4)
        self.worker_count_spin.setToolTip(
            "Number of parallel processes. Each worker uses ~400MB RAM "
            "(YOLO + PaddleOCR models). Default 4."
        )
        parallel_layout.addWidget(self.worker_count_spin)

        parallel_note = QLabel("~400MB RAM per worker")
        parallel_note.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")
        parallel_layout.addWidget(parallel_note)
        parallel_layout.addStretch()

        controls.addWidget(parallel_group)

        # 4. Zone Configuration
        self.zone_widget = ZoneControlWidget()
        controls.addWidget(self.zone_widget)

        # 5. Claude Validation
        claude_group = QGroupBox("Claude Plate Validation")
        claude_layout = QVBoxLayout(claude_group)
        claude_layout.setSpacing(6)

        self.claude_enable_cb = QCheckBox("Enable Claude API validation")
        self.claude_enable_cb.setChecked(False)
        self.claude_enable_cb.toggled.connect(self._on_claude_toggled)
        claude_layout.addWidget(self.claude_enable_cb)

        api_key_row = QHBoxLayout()
        api_key_lbl = QLabel("API Key:")
        api_key_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        api_key_row.addWidget(api_key_lbl)
        self.claude_api_key = QLineEdit()
        self.claude_api_key.setPlaceholderText("sk-ant-...")
        self.claude_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.claude_api_key.setEnabled(False)
        api_key_row.addWidget(self.claude_api_key)
        claude_layout.addLayout(api_key_row)

        model_row = QHBoxLayout()
        model_lbl = QLabel("Model:")
        model_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        model_row.addWidget(model_lbl)
        self.claude_model_combo = QComboBox()
        self.claude_model_combo.addItems([
            "claude-haiku-4-5-20251001",
            "claude-sonnet-4-20250514",
            "claude-opus-4-20250514",
        ])
        self.claude_model_combo.setCurrentIndex(0)
        self.claude_model_combo.setEnabled(False)
        model_row.addWidget(self.claude_model_combo)
        claude_layout.addLayout(model_row)

        threshold_row = QHBoxLayout()
        threshold_lbl = QLabel("Confidence threshold:")
        threshold_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        threshold_row.addWidget(threshold_lbl)
        self.claude_threshold = QDoubleSpinBox()
        self.claude_threshold.setRange(0.0, 1.0)
        self.claude_threshold.setSingleStep(0.05)
        self.claude_threshold.setValue(0.70)
        self.claude_threshold.setDecimals(2)
        self.claude_threshold.setEnabled(False)
        threshold_row.addWidget(self.claude_threshold)
        claude_layout.addLayout(threshold_row)

        self.claude_status_label = QLabel("Disabled")
        self.claude_status_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px;"
        )
        claude_layout.addWidget(self.claude_status_label)

        controls.addWidget(claude_group)

        # 6. Blob Storage Widget
        self.blob_storage_widget = BlobStorageWidget()
        controls.addWidget(self.blob_storage_widget)

        # 7. Status label
        self.status_label = QLabel("Load a job folder to discover videos.")
        self.status_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        controls.addWidget(self.status_label)

        # 8. Continue button
        self.continue_btn = QPushButton("Continue to Processing  >")
        self.continue_btn.setObjectName("primary_btn")
        self.continue_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.continue_btn.setEnabled(False)
        self.continue_btn.clicked.connect(self.continue_clicked.emit)
        controls.addWidget(self.continue_btn)

        controls.addStretch()

        controls_scroll.setWidget(controls_inner)
        content.addWidget(controls_scroll, stretch=2)
        outer.addLayout(content)

    def _connect_signals(self):
        # Job folder -> video discovery
        self.job_folder_widget.videos_selected.connect(self._on_videos_selected)
        self.job_folder_widget.job_loaded.connect(self._on_job_loaded)

        # Zone drawing: control widget requests draw -> preview starts drawing
        self.zone_widget.zone_draw_requested.connect(
            self.video_preview.start_zone_drawing
        )
        # Zone completed on preview -> add to control widget
        self.video_preview.zone_completed.connect(self.zone_widget.add_zone)
        # When zones change, sync overlay on preview
        self.zone_widget.zones_changed.connect(self._on_zones_changed)

    # ── Pre-load from Step 1 ────────────────────────────────────────

    def preload_data(self, scan_result: dict, selected_videos: list[str]):
        """Pre-populate setup page with data from Step 1 folder selection.

        This auto-fills the job folder widget, sets video paths, loads a
        reference frame, and sets direction from the scan result so the
        user doesn't have to re-enter anything.
        """
        self._video_paths = selected_videos
        has_videos = len(selected_videos) > 0

        # Pre-fill the job folder widget display
        job_folder_path = scan_result.get("job_folder_path", "")
        if job_folder_path:
            self.job_folder_widget._path_edit.setText(job_folder_path)
            self.job_folder_widget._root_path = job_folder_path
            self.job_folder_widget._scan_result = scan_result
            self.job_folder_widget._job_number = scan_result.get("job_number", "")
            self.job_folder_widget._job_name = scan_result.get("job_name", "")

            # Show job number/name
            display = scan_result.get("job_number", "")
            job_name = scan_result.get("job_name", "")
            if job_name:
                display += f" — {job_name}"
            if display:
                self.job_folder_widget._job_number_label.setText(display)

            # Set date range from scan
            self.job_folder_widget._auto_set_date_range(scan_result)

            # Populate tree
            self.job_folder_widget._populate_tree(scan_result)

        # Update video summary
        sites = scan_result.get("sites", [])
        total_videos = sum(len(s.get("video_paths", [])) for s in sites)
        site_count = len({s["site_name"] for s in sites})
        if total_videos > 0:
            self.video_summary_label.setText(
                f"Discovered {site_count} site(s) with {total_videos} video(s). "
                f"{len(selected_videos)} selected."
            )
            self.video_summary_label.setStyleSheet(
                f"color: {SUCCESS}; font-size: 12px;"
            )

        # Set direction from scan result if available
        sites_summary = scan_result.get("sites_summary", [])
        if sites_summary:
            direction = sites_summary[0].get("direction", "")
            if direction:
                # Set "towards" to the detected direction
                idx = self.towards_combo.findText(direction)
                if idx >= 0:
                    self.towards_combo.setCurrentIndex(idx)
                # Set "away" to the opposite
                opposites = {"NB": "SB", "SB": "NB", "EB": "WB", "WB": "EB"}
                opp = opposites.get(direction, "")
                if opp:
                    idx = self.away_combo.findText(opp)
                    if idx >= 0:
                        self.away_combo.setCurrentIndex(idx)

        # Enable controls
        self.continue_btn.setEnabled(has_videos)
        self.load_frame_btn.setEnabled(has_videos)

        if has_videos:
            self.status_label.setText(
                f"{len(selected_videos)} video(s) ready. Configure zones and continue."
            )
            self.status_label.setStyleSheet(f"color: {SUCCESS}; font-size: 12px;")

            # Auto-load reference frame from first video
            self._auto_load_reference_frame()

    def _auto_load_reference_frame(self):
        """Auto-populate the video scrubber and seek to a daylight frame."""
        if not self._video_paths:
            return

        # Populate video combo box
        self._video_combo.blockSignals(True)
        self._video_combo.clear()
        for vp in self._video_paths:
            import os
            self._video_combo.addItem(os.path.basename(vp), vp)
        self._video_combo.blockSignals(False)

        # Find the best daylight video (prefer filenames starting 08-16 hrs)
        best_idx = self._find_daylight_video_index()
        if best_idx >= 0:
            self._video_combo.setCurrentIndex(best_idx)
        else:
            self._load_video_into_scrubber(self._video_paths[0])

    def _find_daylight_video_index(self) -> int:
        """Find the first video whose filename suggests daylight hours (07-17).

        Video filenames often follow HHMMSS_HHMMSS.ext patterns.
        Returns the index into _video_paths, or -1 if none found.
        """
        import os
        for i, vp in enumerate(self._video_paths):
            fname = os.path.splitext(os.path.basename(vp))[0]
            time_match = re.match(r"^(\d{2})", fname)
            if time_match:
                hour = int(time_match.group(1))
                if 7 <= hour <= 16:
                    return i
        return -1

    def _on_video_combo_changed(self, index: int):
        """Switch which video the scrubber controls."""
        if index < 0 or index >= len(self._video_paths):
            return
        self._load_video_into_scrubber(self._video_paths[index])

    def _load_video_into_scrubber(self, video_path: str):
        """Open a video, set up the scrubber range, and show a frame."""
        # Release any previous capture
        if hasattr(self, "_scrub_cap") and self._scrub_cap is not None:
            self._scrub_cap.release()
        # Clear frame cache on video switch
        if hasattr(self, "_frame_cache"):
            self._frame_cache.clear()

        self._scrub_cap = cv2.VideoCapture(video_path)
        if not self._scrub_cap.isOpened():
            self._frame_label.setText("Cannot open video")
            return

        total_frames = int(self._scrub_cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = self._scrub_cap.get(cv2.CAP_PROP_FPS) or 25.0
        self._scrub_fps = fps
        self._scrub_total = total_frames

        self._scrubber.blockSignals(True)
        self._scrubber.setMinimum(0)
        self._scrubber.setMaximum(max(0, total_frames - 1))
        self._scrubber.setEnabled(total_frames > 0)

        # Seek to ~30% in (often past dark early morning footage)
        start_frame = min(int(total_frames * 0.3), total_frames - 1) if total_frames > 10 else 0
        self._scrubber.setValue(start_frame)
        self._scrubber.blockSignals(False)

        # Show the frame
        self._seek_and_display(start_frame)

    def _on_scrubber_changed(self, value: int):
        """User moved the scrubber slider — debounce to avoid lag."""
        self._pending_frame = value
        # Update label immediately for responsiveness
        fps = getattr(self, "_scrub_fps", 25.0)
        total = getattr(self, "_scrub_total", 0)
        current_sec = value / fps if fps > 0 else 0
        total_sec = total / fps if fps > 0 else 0
        self._frame_label.setText(
            f"Frame {value}/{total}  |  "
            f"{self._format_time(current_sec)} / {self._format_time(total_sec)}"
        )
        # Debounce the actual seek
        if not hasattr(self, "_scrub_timer"):
            self._scrub_timer = QTimer()
            self._scrub_timer.setSingleShot(True)
            self._scrub_timer.setInterval(80)  # 80ms debounce
            self._scrub_timer.timeout.connect(self._do_debounced_seek)
        self._scrub_timer.start()

    def _do_debounced_seek(self):
        """Perform the actual seek after debounce timer fires."""
        frame_idx = getattr(self, "_pending_frame", 0)
        self._seek_and_display(frame_idx)

    def _seek_and_display(self, frame_idx: int):
        """Seek to a specific frame and display it, with LRU cache."""
        if not hasattr(self, "_scrub_cap") or self._scrub_cap is None:
            return
        if not self._scrub_cap.isOpened():
            return

        # LRU frame cache
        if not hasattr(self, "_frame_cache"):
            self._frame_cache: dict[int, np.ndarray] = {}

        # Check cache first
        if frame_idx in self._frame_cache:
            frame = self._frame_cache[frame_idx]
        else:
            self._scrub_cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = self._scrub_cap.read()
            if not ret:
                return
            # Cache the frame (limit to 20)
            self._frame_cache[frame_idx] = frame
            if len(self._frame_cache) > 20:
                oldest = next(iter(self._frame_cache))
                del self._frame_cache[oldest]

        self._reference_frame = frame
        self.video_preview.update_frame(frame)

        # Update frame label
        fps = getattr(self, "_scrub_fps", 25.0)
        total = getattr(self, "_scrub_total", 0)
        current_sec = frame_idx / fps if fps > 0 else 0
        total_sec = total / fps if fps > 0 else 0
        self._frame_label.setText(
            f"Frame {frame_idx}/{total}  |  "
            f"{self._format_time(current_sec)} / {self._format_time(total_sec)}"
        )

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format seconds as MM:SS."""
        m = int(seconds) // 60
        s = int(seconds) % 60
        return f"{m:02d}:{s:02d}"

    # ── Job folder handling ──────────────────────────────────────────

    def _on_job_loaded(self, result: dict):
        """Update the video summary when a job folder is scanned."""
        sites = result.get("sites", [])
        total_videos = sum(len(s.get("video_paths", [])) for s in sites)
        site_count = len({s["site_name"] for s in sites})
        if total_videos > 0:
            self.video_summary_label.setText(
                f"Discovered {site_count} site(s) with {total_videos} video(s)."
            )
            self.video_summary_label.setStyleSheet(
                f"color: {SUCCESS}; font-size: 12px;"
            )
        else:
            self.video_summary_label.setText("No videos found in job folder.")
            self.video_summary_label.setStyleSheet(
                f"color: {TEXT_MUTED}; font-size: 12px;"
            )

    def _on_videos_selected(self, video_paths: list):
        """Store selected video paths and enable controls."""
        self._video_paths = video_paths
        has_videos = len(video_paths) > 0
        self.continue_btn.setEnabled(has_videos)
        self.load_frame_btn.setEnabled(has_videos)
        if has_videos:
            self.status_label.setText(
                f"{len(video_paths)} video(s) ready. Configure zones and continue."
            )
            self.status_label.setStyleSheet(f"color: {SUCCESS}; font-size: 12px;")
            # Auto-load reference frame when videos are selected on this page too
            self._auto_load_reference_frame()
        else:
            self.status_label.setText("Load a job folder to discover videos.")
            self.status_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")

    # ── Reference frame ──────────────────────────────────────────────

    def _load_reference_frame(self):
        """Load the first frame from the first video for zone setup."""
        if not self._video_paths:
            return
        cap = cv2.VideoCapture(self._video_paths[0])
        ret, frame = cap.read()
        cap.release()
        if ret:
            self._reference_frame = frame
            self.video_preview.update_frame(frame)
            self.status_label.setText("Reference frame loaded. Draw zones if needed.")

    def get_reference_frame(self) -> np.ndarray | None:
        """Return the loaded reference frame, if any."""
        return self._reference_frame

    # ── Zone handling ────────────────────────────────────────────────

    def _on_zones_changed(self):
        self.video_preview.set_zones(
            self.zone_widget.capture_zones,
            self.zone_widget.exclusion_zones,
        )

    # ── Claude toggle ────────────────────────────────────────────────

    def _on_claude_toggled(self, enabled: bool):
        self.claude_api_key.setEnabled(enabled)
        self.claude_model_combo.setEnabled(enabled)
        self.claude_threshold.setEnabled(enabled)
        if enabled:
            self.claude_status_label.setText("Enabled \u2014 API key required")
            self.claude_status_label.setStyleSheet(
                f"color: {SUCCESS}; font-size: 11px;"
            )
        else:
            self.claude_status_label.setText("Disabled")
            self.claude_status_label.setStyleSheet(
                f"color: {TEXT_MUTED}; font-size: 11px;"
            )

    # ── Claude validator helper ──────────────────────────────────────

    def create_claude_validator(self) -> ClaudePlateValidator | None:
        """Build a ClaudePlateValidator if enabled and configured."""
        if not self.claude_enable_cb.isChecked():
            return None
        api_key = self.claude_api_key.text().strip()
        if not api_key:
            self.status_label.setText("Warning: Claude enabled but no API key set")
            self.status_label.setStyleSheet("color: #e67e22; font-size: 12px;")
            return None
        model = self.claude_model_combo.currentText()
        threshold = self.claude_threshold.value()
        return ClaudePlateValidator(
            api_key=api_key,
            model=model,
            confidence_threshold=threshold,
        )

    # ── Public getters ───────────────────────────────────────────────

    def get_video_paths(self) -> list[str]:
        return list(self._video_paths)


# ── Step 3: Processing Page ──────────────────────────────────────────


class _WorkerCard(QFrame):
    """Card displaying stats for a single processing worker."""

    CARD_STYLE = f"""
        _WorkerCard {{
            background: {BG_SECONDARY};
            border: 1px solid {BORDER};
            border-radius: 8px;
            padding: 10px;
        }}
    """

    def __init__(self, worker_id: int, parent=None):
        super().__init__(parent)
        self._worker_id = worker_id
        self.setStyleSheet(self.CARD_STYLE)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # Header row: Worker N + status dot
        header = QHBoxLayout()
        self._title = QLabel(f"Worker {self._worker_id}")
        self._title.setStyleSheet(
            f"color: {NAVY}; font-size: 13px; font-weight: 600; border: none;"
        )
        header.addWidget(self._title)
        header.addStretch()
        self._status_dot = QLabel("\u25cf")
        self._status_dot.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 14px; border: none;"
        )
        header.addWidget(self._status_dot)
        layout.addLayout(header)

        # Current video
        self._video_label = QLabel("Waiting...")
        self._video_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; border: none;"
        )
        self._video_label.setWordWrap(True)
        layout.addWidget(self._video_label)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setValue(0)
        self._progress.setMaximumHeight(8)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(f"""
            QProgressBar {{
                background: {BORDER}; border-radius: 4px; border: none;
            }}
            QProgressBar::chunk {{
                background: {NAVY}; border-radius: 4px;
            }}
        """)
        layout.addWidget(self._progress)

        # Stats row
        stats = QHBoxLayout()
        self._vehicles_label = QLabel("0 vehicles")
        self._vehicles_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; border: none;"
        )
        stats.addWidget(self._vehicles_label)
        stats.addStretch()
        self._percent_label = QLabel("0%")
        self._percent_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; border: none;"
        )
        stats.addWidget(self._percent_label)
        layout.addLayout(stats)

    def set_video(self, filename: str):
        self._video_label.setText(filename)
        self._status_dot.setStyleSheet(
            f"color: {SUCCESS}; font-size: 14px; border: none;"
        )

    def set_progress(self, percent: int):
        self._progress.setValue(percent)
        self._percent_label.setText(f"{percent}%")

    def set_vehicle_count(self, count: int):
        self._vehicles_label.setText(f"{count} vehicles")

    def set_finished(self):
        self._status_dot.setStyleSheet(
            f"color: {SUCCESS}; font-size: 14px; border: none;"
        )
        self._video_label.setText("Complete")
        self._progress.setValue(100)
        self._percent_label.setText("100%")

    def set_error(self, msg: str):
        self._status_dot.setStyleSheet(
            f"color: {DANGER}; font-size: 14px; border: none;"
        )
        self._video_label.setText(f"Error: {msg}")


class ANPRProcessingPage(QWidget):
    """Step 3: Parallel video processing with stats dashboard.

    Replaces the old video preview with a per-worker stats dashboard
    showing progress, estimated time, vehicle counts, and queue status.
    """

    back_to_setup = Signal()
    qa_ready = Signal(object)  # emits VehicleStore when processing completes

    def __init__(self, parent=None):
        super().__init__(parent)
        self._process_manager = None
        self._monitor = None
        self._vehicle_store = None
        self._job_config: JobConfig | None = None
        self._video_paths: list[str] = []
        self._worker_count = 4
        self._worker_cards: dict[int, _WorkerCard] = {}
        self._worker_vehicle_counts: dict[int, int] = {}
        self._worker_progress: dict[int, int] = {}
        self._start_time: float = 0.0
        self._total_videos = 0
        self._finished_videos = 0
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 20)
        layout.setSpacing(12)

        # ── Back button ──────────────────────────────────────────────
        back_row = QHBoxLayout()
        back_btn = QPushButton("<  Back to Setup")
        back_btn.setStyleSheet(BACK_BUTTON_STYLE)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self.back_to_setup.emit)
        back_row.addWidget(back_btn)
        back_row.addStretch()
        layout.addLayout(back_row)

        # ── Process / Stop buttons row ───────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.process_btn = QPushButton("Process Videos")
        self.process_btn.setObjectName("primary_btn")
        self.process_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.process_btn.setEnabled(False)
        self.process_btn.clicked.connect(self._start_processing)
        btn_row.addWidget(self.process_btn)

        self.stop_btn = QPushButton("Stop Processing")
        self.stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_processing)
        btn_row.addWidget(self.stop_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        # ── Overall stats banner ─────────────────────────────────────
        stats_frame = QFrame()
        stats_frame.setStyleSheet(f"""
            QFrame {{
                background: {NAVY_LIGHT};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 12px;
            }}
        """)
        stats_layout = QHBoxLayout(stats_frame)
        stats_layout.setContentsMargins(16, 10, 16, 10)
        stats_layout.setSpacing(24)

        # Overall progress
        progress_col = QVBoxLayout()
        self._overall_percent_label = QLabel("0%")
        self._overall_percent_label.setStyleSheet(
            f"color: {NAVY}; font-size: 28px; font-weight: 700; border: none;"
        )
        self._overall_percent_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress_col.addWidget(self._overall_percent_label)
        overall_sub = QLabel("Overall Progress")
        overall_sub.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; border: none;"
        )
        overall_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress_col.addWidget(overall_sub)
        stats_layout.addLayout(progress_col)

        # Separator
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet(f"color: {BORDER}; border: none;")
        stats_layout.addWidget(sep1)

        # Vehicles detected
        vehicles_col = QVBoxLayout()
        self._total_vehicles_label = QLabel("0")
        self._total_vehicles_label.setStyleSheet(
            f"color: {NAVY}; font-size: 28px; font-weight: 700; border: none;"
        )
        self._total_vehicles_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vehicles_col.addWidget(self._total_vehicles_label)
        veh_sub = QLabel("Vehicles Detected")
        veh_sub.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; border: none;"
        )
        veh_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vehicles_col.addWidget(veh_sub)
        stats_layout.addLayout(vehicles_col)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setStyleSheet(f"color: {BORDER}; border: none;")
        stats_layout.addWidget(sep2)

        # Flagged for review
        flagged_col = QVBoxLayout()
        self._flagged_label = QLabel("0")
        self._flagged_label.setStyleSheet(
            f"color: {WARNING}; font-size: 28px; font-weight: 700; border: none;"
        )
        self._flagged_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        flagged_col.addWidget(self._flagged_label)
        flag_sub = QLabel("Flagged for Review")
        flag_sub.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; border: none;"
        )
        flag_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        flagged_col.addWidget(flag_sub)
        stats_layout.addLayout(flagged_col)

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.VLine)
        sep3.setStyleSheet(f"color: {BORDER}; border: none;")
        stats_layout.addWidget(sep3)

        # Elapsed / ETA
        time_col = QVBoxLayout()
        self._time_label = QLabel("--:--")
        self._time_label.setStyleSheet(
            f"color: {NAVY}; font-size: 28px; font-weight: 700; border: none;"
        )
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        time_col.addWidget(self._time_label)
        self._time_sub_label = QLabel("Elapsed / ETA")
        self._time_sub_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; border: none;"
        )
        self._time_sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        time_col.addWidget(self._time_sub_label)
        stats_layout.addLayout(time_col)

        sep4 = QFrame()
        sep4.setFrameShape(QFrame.Shape.VLine)
        sep4.setStyleSheet(f"color: {BORDER}; border: none;")
        stats_layout.addWidget(sep4)

        # Queue / Videos
        queue_col = QVBoxLayout()
        self._queue_label = QLabel("0 / 0")
        self._queue_label.setStyleSheet(
            f"color: {NAVY}; font-size: 28px; font-weight: 700; border: none;"
        )
        self._queue_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        queue_col.addWidget(self._queue_label)
        queue_sub = QLabel("Videos Done / Total")
        queue_sub.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; border: none;"
        )
        queue_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        queue_col.addWidget(queue_sub)
        stats_layout.addLayout(queue_col)

        layout.addWidget(stats_frame)

        # ── Overall progress bar ─────────────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximumHeight(10)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background: {BORDER}; border-radius: 5px;
            }}
            QProgressBar::chunk {{
                background: {NAVY}; border-radius: 5px;
            }}
        """)
        layout.addWidget(self.progress_bar)

        # ── Status label ─────────────────────────────────────────────
        self.status_label = QLabel("Ready — configure settings and click Process Videos")
        self.status_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        layout.addWidget(self.status_label)

        # ── Worker cards grid ────────────────────────────────────────
        self._worker_grid_container = QWidget()
        self._worker_grid = QGridLayout(self._worker_grid_container)
        self._worker_grid.setSpacing(10)
        self._worker_grid.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._worker_grid_container)

        # ── Results summary table ────────────────────────────────────
        results_group = QGroupBox("Recent Detections")
        results_layout = QVBoxLayout(results_group)

        self.results_table = QTableWidget()
        self.results_table.setColumnCount(7)
        self.results_table.setHorizontalHeaderLabels(
            ["ID", "Plate", "Time", "Confidence", "Valid", "Direction", "Video"]
        )
        self.results_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.results_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setSortingEnabled(True)
        self.results_table.setMaximumHeight(200)
        results_layout.addWidget(self.results_table)

        self.count_label = QLabel("Vehicles: 0  |  Flagged: 0")
        self.count_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        results_layout.addWidget(self.count_label)
        layout.addWidget(results_group, stretch=1)

        # ── Export + QA buttons ──────────────────────────────────────
        bottom_row = QHBoxLayout()

        self.export_btn = QPushButton("Export to Excel")
        self.export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._export_results)
        bottom_row.addWidget(self.export_btn)

        bottom_row.addStretch()

        self.qa_btn = QPushButton("Continue to QA Review  >")
        self.qa_btn.setObjectName("primary_btn")
        self.qa_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.qa_btn.setEnabled(False)
        self.qa_btn.clicked.connect(self._go_to_qa)
        bottom_row.addWidget(self.qa_btn)

        layout.addLayout(bottom_row)

        # ── Timer for updating elapsed / ETA ─────────────────────────
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._update_time_display)

    # ── Worker card management ───────────────────────────────────────

    def _create_worker_cards(self, count: int):
        """Create worker cards in a grid layout (max 4 per row)."""
        # Clear old cards
        for card in self._worker_cards.values():
            card.deleteLater()
        self._worker_cards.clear()
        self._worker_vehicle_counts.clear()
        self._worker_progress.clear()

        # Remove old items from grid
        while self._worker_grid.count():
            item = self._worker_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        cols = min(count, 4)
        for i in range(count):
            card = _WorkerCard(i)
            row = i // cols
            col = i % cols
            self._worker_grid.addWidget(card, row, col)
            self._worker_cards[i] = card
            self._worker_vehicle_counts[i] = 0
            self._worker_progress[i] = 0

    # ── Processing ───────────────────────────────────────────────────

    def set_processing_data(
        self,
        video_paths: list[str],
        capture_zones: list,
        exclusion_zones: list,
        towards_label: str,
        away_label: str,
        claude_validator: ClaudePlateValidator | None,
        blob_storage,
        job_config: JobConfig | None,
        worker_count: int = 4,
    ):
        """Receive all configuration from setup pages before processing."""
        self._video_paths = video_paths
        self._capture_zones = capture_zones
        self._exclusion_zones = exclusion_zones
        self._towards_label = towards_label
        self._away_label = away_label
        self._claude_validator = claude_validator
        self._blob_storage = blob_storage
        self._job_config = job_config
        self._worker_count = worker_count
        self._total_videos = len(video_paths)
        self.process_btn.setEnabled(len(video_paths) > 0)

        # Update queue display
        self._queue_label.setText(f"0 / {self._total_videos}")
        self.status_label.setText(
            f"{len(video_paths)} video(s) ready with {worker_count} workers — "
            f"click Process Videos to start"
        )

    def _start_processing(self):
        import tempfile
        from src.engine.process_manager import (
            ProcessManager, create_chunked_assignments,
        )
        from src.engine.monitor_bridge import MonitorBridge
        from src.anpr.anpr_subprocess import ANPRSubprocessWorker
        from src.anpr.vehicle_store import VehicleStore

        paths = self._video_paths
        if not paths:
            return

        # Reset UI
        self.results_table.setSortingEnabled(False)
        self.results_table.setRowCount(0)
        self.count_label.setText("Vehicles: 0  |  Flagged: 0")
        self.progress_bar.setValue(0)
        self._overall_percent_label.setText("0%")
        self._total_vehicles_label.setText("0")
        self._flagged_label.setText("0")
        self._time_label.setText("00:00")
        self._time_sub_label.setText("Elapsed")
        self._finished_videos = 0
        self.export_btn.setEnabled(False)
        self.qa_btn.setEnabled(False)
        self.process_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        # Create temp dir for image crops
        self._output_dir = tempfile.mkdtemp(prefix="anpr_")

        # Create vehicle store
        self._vehicle_store = VehicleStore()

        # Auto-detect GPU
        use_gpu = False
        try:
            import torch
            use_gpu = torch.cuda.is_available()
        except ImportError:
            pass

        # Create chunked assignments — automatically splits long videos
        # into ~15 min chunks across workers, with 30s overlap for dedup.
        worker_count = min(self._worker_count, max(len(paths), 4))
        assignments = create_chunked_assignments(
            video_paths=paths,
            max_workers=worker_count,
            chunk_duration_minutes=15.0,
            overlap_seconds=30,
            use_gpu=use_gpu,
        )

        if not assignments:
            self.status_label.setText("No valid video files found")
            self._reset_controls()
            return

        # Count total chunks for queue display
        total_chunks = sum(
            len(a.chunks) for a in assignments
        )
        self._total_videos = total_chunks
        self._queue_label.setText(f"0 / {total_chunks}")

        # Create worker cards
        self._create_worker_cards(len(assignments))

        # Build config for workers
        corrections_path = ""
        if self._job_config and self._job_config.job_folder_path:
            corrections_path = os.path.join(
                self._job_config.job_folder_path, "anpr_corrections.json"
            )

        config = {
            "model_path": "yolov8n.pt",
            "confidence": 0.4,
            "frame_skip": 3,
            "capture_zones": self._capture_zones,
            "exclusion_zones": self._exclusion_zones,
            "towards_label": self._towards_label,
            "away_label": self._away_label,
            "output_dir": self._output_dir,
            "corrections_path": corrections_path,
            "overlay_ocr_interval": 30,
        }

        # Create and start ProcessManager
        self._process_manager = ProcessManager()
        self._process_manager.configure(assignments, ANPRSubprocessWorker, config)
        result_queue = self._process_manager.start()

        # Track time
        self._start_time = time.time()
        self._tick_timer.start()

        gpu_tag = " (GPU)" if use_gpu else " (CPU)"
        chunk_info = (
            f" ({total_chunks} chunks)" if total_chunks > len(paths) else ""
        )
        self.status_label.setText(
            f"Processing {len(paths)} video(s) with "
            f"{len(assignments)} workers{gpu_tag}{chunk_info}..."
        )

        # Create MonitorBridge to poll results
        self._monitor = MonitorBridge(result_queue, expected_streams=len(assignments))
        self._monitor.stream_progress.connect(self._on_progress)
        self._monitor.stream_status.connect(self._on_status_update)
        self._monitor.stream_result.connect(self._on_result)
        self._monitor.stream_error.connect(self._on_error)
        self._monitor.stream_finished.connect(self._on_stream_finished)
        self._monitor.video_started.connect(self._on_video_started)
        self._monitor.all_finished.connect(self._on_all_finished)
        self._monitor.start()

    def _stop_processing(self):
        self._tick_timer.stop()
        if self._monitor:
            self._monitor.stop()
            self._monitor.wait(2000)
        if self._process_manager:
            self._process_manager.stop()
        self.status_label.setText("Processing stopped")
        self._reset_controls()

    # ── Time display ─────────────────────────────────────────────────

    def _update_time_display(self):
        """Update elapsed time and ETA every second."""
        if self._start_time <= 0:
            return
        elapsed = time.time() - self._start_time
        elapsed_str = self._fmt_duration(elapsed)

        # Compute ETA from overall progress
        overall = self.progress_bar.value()
        if overall > 0 and overall < 100:
            total_est = elapsed / (overall / 100.0)
            remaining = total_est - elapsed
            self._time_label.setText(elapsed_str)
            self._time_sub_label.setText(
                f"Elapsed  |  ~{self._fmt_duration(remaining)} remaining"
            )
        else:
            self._time_label.setText(elapsed_str)
            self._time_sub_label.setText("Elapsed")

    @staticmethod
    def _fmt_duration(seconds: float) -> str:
        s = int(seconds)
        if s < 3600:
            return f"{s // 60:02d}:{s % 60:02d}"
        h = s // 3600
        m = (s % 3600) // 60
        return f"{h}:{m:02d}:{s % 60:02d}"

    # ── Signal handlers ──────────────────────────────────────────────

    @Slot(int, int)
    def _on_progress(self, stream_id: int, overall_percent: int):
        # Update per-worker progress
        self._worker_progress[stream_id] = overall_percent
        if stream_id in self._worker_cards:
            self._worker_cards[stream_id].set_progress(overall_percent)

        # Compute true overall from all workers
        if self._worker_progress:
            avg = sum(self._worker_progress.values()) // len(self._worker_progress)
        else:
            avg = overall_percent
        self.progress_bar.setValue(avg)
        self._overall_percent_label.setText(f"{avg}%")

    @Slot(int, str)
    def _on_video_started(self, stream_id: int, filename: str):
        self.status_label.setText(f"Worker {stream_id}: {filename}")
        if stream_id in self._worker_cards:
            self._worker_cards[stream_id].set_video(filename)

    @Slot(int, dict)
    def _on_stream_finished(self, stream_id: int, payload: dict):
        """A single worker finished all its videos."""
        if stream_id in self._worker_cards:
            self._worker_cards[stream_id].set_finished()
        # Count finished videos from this worker's assignments
        self._finished_videos += 1
        self._queue_label.setText(
            f"{self._finished_videos} / {self._total_videos}"
        )

    @Slot(int, dict)
    def _on_result(self, stream_id: int, result: dict):
        """Process a vehicle detection result from a worker."""
        if result.get("type") != "vehicle_detection":
            return

        vehicle = self._vehicle_store.add_detection(result)

        # Update per-worker vehicle count
        self._worker_vehicle_counts[stream_id] = (
            self._worker_vehicle_counts.get(stream_id, 0) + 1
        )
        if stream_id in self._worker_cards:
            self._worker_cards[stream_id].set_vehicle_count(
                self._worker_vehicle_counts[stream_id]
            )

        # Only update table for new best readings
        if result.get("is_new_best", True):
            self._update_table_row(vehicle)

        # Update overall stats
        store = self._vehicle_store
        self._total_vehicles_label.setText(str(store.total_vehicles))
        self._flagged_label.setText(str(store.total_flagged))
        self.count_label.setText(
            f"Vehicles: {store.total_vehicles}  |  Flagged: {store.total_flagged}"
        )

    def _update_table_row(self, vehicle):
        """Add or update a row in the results table for a vehicle."""
        # Find existing row by vehicle_id
        for row in range(self.results_table.rowCount()):
            item = self.results_table.item(row, 0)
            if item and item.text() == vehicle.vehicle_id:
                # Update existing row
                best = vehicle.best_reading
                self.results_table.setItem(row, 1, QTableWidgetItem(best.plate_text))
                self.results_table.setItem(row, 2, QTableWidgetItem(best.real_time))
                self.results_table.setItem(row, 3, QTableWidgetItem(f"{best.confidence:.0f}%"))
                self.results_table.setItem(row, 4, QTableWidgetItem("Yes" if best.is_valid_format else "No"))
                self.results_table.setItem(row, 5, QTableWidgetItem(vehicle.direction))
                self.results_table.setItem(row, 6, QTableWidgetItem(best.video_file))
                return

        # Add new row
        row = self.results_table.rowCount()
        self.results_table.insertRow(row)
        best = vehicle.best_reading
        self.results_table.setItem(row, 0, QTableWidgetItem(vehicle.vehicle_id))
        self.results_table.setItem(row, 1, QTableWidgetItem(best.plate_text))
        self.results_table.setItem(row, 2, QTableWidgetItem(best.real_time))
        self.results_table.setItem(row, 3, QTableWidgetItem(f"{best.confidence:.0f}%"))
        self.results_table.setItem(row, 4, QTableWidgetItem("Yes" if best.is_valid_format else "No"))
        self.results_table.setItem(row, 5, QTableWidgetItem(vehicle.direction))
        self.results_table.setItem(row, 6, QTableWidgetItem(best.video_file))

    @Slot(int, str)
    def _on_status_update(self, stream_id: int, text: str):
        self.status_label.setText(f"[{stream_id}] {text}")

    @Slot(dict)
    def _on_all_finished(self, summary: dict):
        self._tick_timer.stop()
        self._reset_controls()
        self.results_table.setSortingEnabled(True)
        self.progress_bar.setValue(100)
        self._overall_percent_label.setText("100%")

        # Final time
        if self._start_time > 0:
            elapsed = time.time() - self._start_time
            self._time_label.setText(self._fmt_duration(elapsed))
            self._time_sub_label.setText("Total Time")

        self._queue_label.setText(
            f"{self._total_videos} / {self._total_videos}"
        )

        store = self._vehicle_store
        if store:
            self._total_vehicles_label.setText(str(store.total_vehicles))
            self._flagged_label.setText(str(store.total_flagged))
            self.export_btn.setEnabled(store.total_vehicles > 0)
            self.qa_btn.setEnabled(store.total_vehicles > 0)
            self.status_label.setText(
                f"Complete — {store.total_vehicles} vehicles detected, "
                f"{store.total_flagged} flagged for review"
            )
            self.status_label.setStyleSheet(f"color: {SUCCESS}; font-size: 12px;")

    @Slot(int, str)
    def _on_error(self, stream_id: int, message: str):
        self.status_label.setText(f"Error (worker {stream_id}): {message}")
        self.status_label.setStyleSheet("color: #e74c3c; font-size: 12px;")
        if stream_id in self._worker_cards:
            self._worker_cards[stream_id].set_error(message[:40])

    def _reset_controls(self):
        self.process_btn.setEnabled(len(self._video_paths) > 0)
        self.stop_btn.setEnabled(False)

    def _go_to_qa(self):
        """Navigate to QA Review page."""
        if self._vehicle_store:
            self.qa_ready.emit(self._vehicle_store)

    def get_vehicle_store(self):
        """Return the vehicle store for external access."""
        return self._vehicle_store

    def _export_results(self):
        if not self._vehicle_store or self._vehicle_store.total_vehicles == 0:
            return

        from src.common.survey_widget import SurveyInfo

        config = self._job_config
        if config is not None:
            site_number = ""
            site_name = ""
            if config.sites:
                site_number = config.sites[0].site_number
                site_name = config.sites[0].site_name
            survey = SurveyInfo(
                job_number=config.job_number,
                job_name=config.job_name,
                site_number=site_number,
                site_name=site_name,
                camera_number="",
            )
        else:
            survey = SurveyInfo()

        # Convert vehicle store to legacy format for export
        results = self._vehicle_store.to_export_list()
        legacy_results = []
        for r in results:
            legacy_results.append({
                "plate": r["plate"],
                "time": r["real_time"],
                "real_time": r["real_time"],
                "confidence": r["confidence"],
                "valid": r["is_valid"],
                "direction": r["direction"],
                "video_file": r["video_file"],
            })

        site = survey.site_number or "Unknown"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Excel Report",
            f"ANPR_Report_{site}.xlsx",
            "Excel Files (*.xlsx)",
        )
        if path:
            export_anpr_results(legacy_results, survey, path)
            self.status_label.setText(f"Exported to {path}")


# ── Main ANPR Page (4-step stacked wizard container) ─────────────────


PAGE_FOLDER = 0
PAGE_SETUP = 1
PAGE_PROCESSING = 2
PAGE_QA = 3


class _ANPRFolderPage(QWidget):
    """Step 1: Job folder selection and video discovery for ANPR."""

    folder_ready = Signal(dict)  # scan result dict
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
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
        title = QLabel("ANPR Data Extraction — Select Job Folder")
        title.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 20px; font-weight: 700; padding: 4px 0;"
        )
        layout.addWidget(title)

        # Job folder widget
        self.job_folder_widget = JobFolderWidget()
        self.job_folder_widget.videos_selected.connect(self._on_videos_confirmed)
        layout.addWidget(self.job_folder_widget)

        layout.addStretch()

    def _on_videos_confirmed(self, video_paths: list):
        """Videos confirmed — emit scan result for Step 2 to consume."""
        info = self.job_folder_widget.get_job_info()
        info["selected_videos"] = video_paths
        self.folder_ready.emit(info)

    def get_selected_videos(self) -> list[str]:
        return self.job_folder_widget.get_selected_videos()


class ANPRPage(QWidget):
    """ANPR module container with 4-step wizard.

    Page 0: Folder selection  (select job folder, discover videos)
    Page 1: Setup page        (direction, zones, Claude, blob)
    Page 2: Processing page   (parallel processing, vehicle tracking, results)
    Page 3: QA Review page    (vehicle cards, corrections, AI validation, export)
    """

    def __init__(self, on_back=None, parent=None):
        super().__init__(parent)
        self._on_back = on_back
        self._job_config: JobConfig | None = None
        self._selected_videos: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Step indicator ───────────────────────────────────────────
        self._step_indicator = _StepIndicator(
            ["Folder Selection", "Setup & Config", "Processing", "QA Review"]
        )
        layout.addWidget(self._step_indicator)

        # ── Stacked pages ────────────────────────────────────────────
        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        # Page 0: Folder Selection
        self.folder_page = _ANPRFolderPage()
        self._stack.addWidget(self.folder_page)

        # Page 1: Setup (direction, zones, Claude, blob, worker count)
        self.setup_page = ANPRSetupPage()
        self._stack.addWidget(self.setup_page)

        # Page 2: Processing
        self.processing_page = ANPRProcessingPage()
        self._stack.addWidget(self.processing_page)

        # Page 3: QA Review
        self.qa_page = ANPRQAReviewPage()
        self._stack.addWidget(self.qa_page)

        # ── Wire navigation signals ──────────────────────────────────
        # Page 0 -> back to menu / forward to page 1
        self.folder_page.back_requested.connect(self._go_back)
        self.folder_page.folder_ready.connect(self._go_to_setup)

        # Page 1 -> back to page 0 / forward to page 2
        self.setup_page.back_clicked.connect(self._go_to_folder)
        self.setup_page.continue_clicked.connect(self._go_to_processing)

        # Page 2 -> back to page 1 / forward to page 3
        self.processing_page.back_to_setup.connect(self._go_to_setup_page)
        self.processing_page.qa_ready.connect(self._go_to_qa)

        # Page 3 -> back to page 2
        self.qa_page.back_to_processing.connect(self._go_to_processing_page)

        # Start on page 0
        self._stack.setCurrentIndex(PAGE_FOLDER)
        self._step_indicator.set_active(PAGE_FOLDER)

    # ── Navigation ───────────────────────────────────────────────────

    def _go_to_setup(self, scan_result: dict | None = None):
        """Move from Step 1 to Step 2, passing scan data for auto-fill."""
        if scan_result:
            self._selected_videos = scan_result.get("selected_videos", [])
            self._scan_result = scan_result
            # Pre-populate Step 2 with folder scan data + selected videos
            self.setup_page.preload_data(scan_result, self._selected_videos)
        self._stack.setCurrentIndex(PAGE_SETUP)
        self._step_indicator.set_active(PAGE_SETUP)

    def _go_to_folder(self):
        """Move back from Step 2 to Step 1."""
        self._stack.setCurrentIndex(PAGE_FOLDER)
        self._step_indicator.set_active(PAGE_FOLDER)

    def _go_to_processing(self):
        """Transfer all config from Step 1+2 to Step 3 and switch."""
        video_paths = self.setup_page.get_video_paths()
        if not video_paths:
            video_paths = self._selected_videos

        # Build a basic JobConfig from scan data (no classification for ANPR)
        scan = getattr(self, "_scan_result", {})
        self._job_config = JobConfig(
            job_number=scan.get("job_number", ""),
            job_name=scan.get("job_name", ""),
            module_type="anpr",
            job_folder_path=scan.get("job_folder_path", ""),
        )

        self.processing_page.set_processing_data(
            video_paths=video_paths,
            capture_zones=self.setup_page.zone_widget.capture_zones,
            exclusion_zones=self.setup_page.zone_widget.exclusion_zones,
            towards_label=self.setup_page.towards_combo.currentText(),
            away_label=self.setup_page.away_combo.currentText(),
            claude_validator=self.setup_page.create_claude_validator(),
            blob_storage=self.setup_page.blob_storage_widget.get_storage(),
            job_config=self._job_config,
            worker_count=self.setup_page.worker_count_spin.value(),
        )

        self._stack.setCurrentIndex(PAGE_PROCESSING)
        self._step_indicator.set_active(PAGE_PROCESSING)

    def _go_to_qa(self, vehicle_store):
        """Move from Step 3 to Step 4 (QA Review) with processed data."""
        from src.anpr.ml_feedback import MLFeedbackStore

        # Create ML feedback store for recording corrections
        ml_feedback = None
        if self._job_config and self._job_config.job_folder_path:
            corrections_path = os.path.join(
                self._job_config.job_folder_path, "anpr_corrections.json"
            )
            ml_feedback = MLFeedbackStore(corrections_path)

        # Get Claude validator from setup page (if configured)
        claude_validator = self.setup_page.create_claude_validator()

        self.qa_page.set_data(
            vehicle_store=vehicle_store,
            ml_feedback=ml_feedback,
            claude_validator=claude_validator,
            job_config=self._job_config,
        )

        self._stack.setCurrentIndex(PAGE_QA)
        self._step_indicator.set_active(PAGE_QA)

    def _go_to_setup_page(self):
        """Move back from Step 3 to Step 2."""
        self.processing_page._stop_processing()
        self._stack.setCurrentIndex(PAGE_SETUP)
        self._step_indicator.set_active(PAGE_SETUP)

    def _go_to_processing_page(self):
        """Move back from Step 4 (QA) to Step 3 (Processing)."""
        self._stack.setCurrentIndex(PAGE_PROCESSING)
        self._step_indicator.set_active(PAGE_PROCESSING)

    def _go_back(self):
        """Navigate back to the main menu."""
        self.processing_page._stop_processing()
        if self._on_back:
            self._on_back()
