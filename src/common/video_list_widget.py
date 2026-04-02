"""Multi-video file list widget with background OCR and drag-and-drop."""

import logging

import cv2
import numpy as np
from PySide6.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QFileDialog,
    QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QThread

from src.common.theme import TEXT_MUTED, SUCCESS
from src.common.utils import get_video_info, format_duration

logger = logging.getLogger(__name__)

# Supported video extensions for drag-and-drop filtering
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".ts"}


class _OverlayOCRWorker(QThread):
    """Runs overlay OCR in a background thread so the UI doesn't freeze."""

    finished = Signal(dict)   # OCR result dict
    error = Signal(str)

    def __init__(self, frame: np.ndarray, parent=None):
        super().__init__(parent)
        self._frame = frame

    def run(self):
        try:
            from src.common.overlay_ocr import OverlayOCR

            ocr = OverlayOCR()
            result = ocr.detect_from_frame(self._frame)
            self.finished.emit(result)
        except Exception as e:
            logger.warning("Background overlay OCR failed: %s", e)
            self.error.emit(str(e))


class VideoListWidget(QGroupBox):
    """Multi-video file list with add/remove, drag-and-drop, and background
    overlay auto-detection.

    Emits overlay_detected when OCR completes on the first video's first frame.
    Emits first_frame_ready with the BGR frame for preview.
    Emits videos_changed whenever the file list changes.
    """

    overlay_detected = Signal(dict)
    first_frame_ready = Signal(object)
    videos_changed = Signal(list)

    def __init__(self, parent=None):
        super().__init__("Video Files", parent)
        self._video_paths: list[str] = []
        self._video_info: dict[str, dict] = {}
        self._overlay_result: dict | None = None
        self._first_frame: np.ndarray | None = None
        self._ocr_worker: _OverlayOCRWorker | None = None
        self._build_ui()
        self.setAcceptDrops(True)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Buttons row
        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("Add Videos")
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.clicked.connect(self._add_videos)
        btn_row.addWidget(self.add_btn)

        self.remove_btn = QPushButton("Remove")
        self.remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove_btn.clicked.connect(self._remove_selected)
        btn_row.addWidget(self.remove_btn)

        self.clear_btn = QPushButton("Clear All")
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.clicked.connect(self._clear_all)
        btn_row.addWidget(self.clear_btn)

        layout.addLayout(btn_row)

        # File list
        self.file_list = QListWidget()
        self.file_list.setMaximumHeight(120)
        self.file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        layout.addWidget(self.file_list)

        # Info label
        self.info_label = QLabel("No videos loaded  —  drag && drop or click Add Videos")
        self.info_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

    # ---- Drag-and-drop support ----

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = []
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if any(local.lower().endswith(ext) for ext in VIDEO_EXTENSIONS):
                paths.append(local)
        if paths:
            self._ingest_paths(paths)
            event.acceptProposedAction()

    # ---- Public API ----

    def add_videos(self, paths: list[str]):
        """Programmatically add videos (used by JobFolderWidget integration)."""
        self._ingest_paths(paths)

    def get_video_paths(self) -> list[str]:
        return self._video_paths.copy()

    def get_total_frames(self) -> int:
        return sum(v.get("frames", 0) for v in self._video_info.values())

    def get_overlay_result(self) -> dict | None:
        return self._overlay_result

    def get_first_frame(self) -> np.ndarray | None:
        return self._first_frame

    # ---- Internal ----

    def _add_videos(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Video Files",
            "",
            "Video Files (*.mp4 *.avi *.mkv *.mov *.wmv);;All Files (*)",
        )
        if paths:
            self._ingest_paths(paths)

    def _ingest_paths(self, paths: list[str]):
        """Common logic for file dialog and drag-and-drop."""
        is_first = len(self._video_paths) == 0

        for path in paths:
            if path in self._video_paths:
                continue
            self._video_paths.append(path)

            info = get_video_info(path)
            self._video_info[path] = info

            filename = path.replace("\\", "/").rsplit("/", 1)[-1]
            duration_str = format_duration(info.get("duration", 0))
            item = QListWidgetItem(f"{filename}  ({duration_str})")
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.file_list.addItem(item)

        # Run overlay OCR on first video's first frame (background thread)
        if is_first and self._video_paths:
            self._detect_overlay_async(self._video_paths[0])

        self._update_info()
        self.videos_changed.emit(self._video_paths.copy())

    def _remove_selected(self):
        for item in self.file_list.selectedItems():
            path = item.data(Qt.ItemDataRole.UserRole)
            if path in self._video_paths:
                self._video_paths.remove(path)
                self._video_info.pop(path, None)
            self.file_list.takeItem(self.file_list.row(item))

        self._update_info()
        self.videos_changed.emit(self._video_paths.copy())

    def _clear_all(self):
        if not self._video_paths:
            return
        reply = QMessageBox.question(
            self,
            "Clear All Videos",
            f"Remove all {len(self._video_paths)} videos from the list?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._video_paths.clear()
        self._video_info.clear()
        self._overlay_result = None
        self._first_frame = None
        self.file_list.clear()
        self._update_info()
        self.videos_changed.emit([])

    def _detect_overlay_async(self, video_path: str):
        """Run overlay OCR in a background thread to avoid freezing the UI."""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return

        ret, frame = cap.read()
        cap.release()

        if not ret:
            return

        self._first_frame = frame
        self.first_frame_ready.emit(frame)

        self._ocr_worker = _OverlayOCRWorker(frame, parent=self)
        self._ocr_worker.finished.connect(self._on_ocr_finished)
        self._ocr_worker.start()

    def _on_ocr_finished(self, result: dict):
        self._overlay_result = result
        self.overlay_detected.emit(result)
        self._ocr_worker = None

    def _update_info(self):
        count = len(self._video_paths)
        if count == 0:
            self.info_label.setText("No videos loaded  —  drag && drop or click Add Videos")
            self.info_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        else:
            total_dur = sum(v.get("duration", 0) for v in self._video_info.values())
            total_frames = sum(v.get("frames", 0) for v in self._video_info.values())
            dur_str = format_duration(total_dur)
            self.info_label.setText(
                f"{count} video{'s' if count > 1 else ''}  |  {dur_str} total  |  "
                f"{total_frames:,} frames"
            )
            self.info_label.setStyleSheet(f"color: {SUCCESS}; font-size: 11px;")
