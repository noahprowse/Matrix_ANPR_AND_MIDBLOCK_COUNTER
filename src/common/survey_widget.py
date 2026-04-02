"""Reusable survey details form widget for both ANPR and Counter modules."""

import json
import logging
from dataclasses import dataclass, asdict

from PySide6.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QMessageBox,
)
from PySide6.QtCore import Qt

from src.common.theme import TEXT_SECONDARY

logger = logging.getLogger(__name__)


@dataclass
class SurveyInfo:
    """Survey metadata for Excel export headers."""
    job_number: str = ""
    job_name: str = ""
    site_number: str = ""
    site_name: str = ""
    camera_number: str = ""


class SurveyWidget(QGroupBox):
    """Form widget for entering survey details.

    Used by both ANPR and Counter pages.  Camera number can be
    auto-populated from video overlay OCR.  Supports saving/loading
    survey sessions to JSON.
    """

    def __init__(self, parent=None):
        super().__init__("Survey Details", parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Row 1: Job Number + Job Name
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        job_num_col = QVBoxLayout()
        lbl = QLabel("Job Number:")
        lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        self.job_number = QLineEdit()
        self.job_number.setPlaceholderText("e.g. J2024-001")
        self.job_number.setMaxLength(30)
        job_num_col.addWidget(lbl)
        job_num_col.addWidget(self.job_number)
        row1.addLayout(job_num_col)

        job_name_col = QVBoxLayout()
        lbl = QLabel("Job Name:")
        lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        self.job_name = QLineEdit()
        self.job_name.setPlaceholderText("e.g. Pacific Hwy Survey")
        self.job_name.setMaxLength(100)
        job_name_col.addWidget(lbl)
        job_name_col.addWidget(self.job_name)
        row1.addLayout(job_name_col)

        layout.addLayout(row1)

        # Row 2: Site Number + Site Name
        row2 = QHBoxLayout()
        row2.setSpacing(8)

        site_num_col = QVBoxLayout()
        lbl = QLabel("Site Number:")
        lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        self.site_number = QLineEdit()
        self.site_number.setPlaceholderText("e.g. S001")
        self.site_number.setMaxLength(20)
        site_num_col.addWidget(lbl)
        site_num_col.addWidget(self.site_number)
        row2.addLayout(site_num_col)

        site_name_col = QVBoxLayout()
        lbl = QLabel("Site Name:")
        lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        self.site_name = QLineEdit()
        self.site_name.setPlaceholderText("e.g. Pacific Hwy / Main St")
        self.site_name.setMaxLength(100)
        site_name_col.addWidget(lbl)
        site_name_col.addWidget(self.site_name)
        row2.addLayout(site_name_col)

        layout.addLayout(row2)

        # Row 3: Camera Number (auto-filled from OCR)
        cam_col = QVBoxLayout()
        lbl = QLabel("Camera Number (auto-detected from video):")
        lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        self.camera_number = QLineEdit()
        self.camera_number.setPlaceholderText("Auto-detected or enter manually")
        self.camera_number.setMaxLength(20)
        cam_col.addWidget(lbl)
        cam_col.addWidget(self.camera_number)
        layout.addLayout(cam_col)

        # Save / Load session buttons
        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save Session")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setToolTip("Save survey details to file for later reuse")
        save_btn.clicked.connect(self._save_session)
        btn_row.addWidget(save_btn)

        load_btn = QPushButton("Load Session")
        load_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        load_btn.setToolTip("Load previously saved survey details")
        load_btn.clicked.connect(self._load_session)
        btn_row.addWidget(load_btn)
        layout.addLayout(btn_row)

    def set_camera_number(self, number: str):
        """Auto-fill camera number from overlay OCR."""
        if number:
            self.camera_number.setText(number)

    def get_info(self) -> SurveyInfo:
        """Return current survey details."""
        return SurveyInfo(
            job_number=self.job_number.text().strip(),
            job_name=self.job_name.text().strip(),
            site_number=self.site_number.text().strip(),
            site_name=self.site_name.text().strip(),
            camera_number=self.camera_number.text().strip(),
        )

    def _save_session(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Survey Session", "survey_session.json", "JSON Files (*.json)",
        )
        if not path:
            return
        try:
            with open(path, "w") as f:
                json.dump(asdict(self.get_info()), f, indent=2)
            logger.info("Session saved to %s", path)
        except Exception as e:
            logger.error("Failed to save session: %s", e)

    def _load_session(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Survey Session", "", "JSON Files (*.json)",
        )
        if not path:
            return
        try:
            with open(path) as f:
                data = json.load(f)
            self.job_number.setText(data.get("job_number", ""))
            self.job_name.setText(data.get("job_name", ""))
            self.site_number.setText(data.get("site_number", ""))
            self.site_name.setText(data.get("site_name", ""))
            self.camera_number.setText(data.get("camera_number", ""))
            logger.info("Session loaded from %s", path)
        except Exception as e:
            logger.error("Failed to load session: %s", e)
            QMessageBox.warning(self, "Load Failed", f"Could not load session:\n{e}")
