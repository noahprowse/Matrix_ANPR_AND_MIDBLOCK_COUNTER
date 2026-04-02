"""Reusable video frame display widget."""

import cv2
import numpy as np
from PySide6.QtWidgets import QLabel
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtCore import Qt


class VideoPreviewWidget(QLabel):
    """Displays OpenCV frames scaled to fit the widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(640, 360)
        self.setStyleSheet("background-color: #0a0a1a; border-radius: 8px;")
        self.setText("No video loaded")

    def update_frame(self, frame: np.ndarray):
        """Update display with a BGR OpenCV frame."""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)
        scaled = pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)

    def clear_frame(self):
        """Reset to placeholder text."""
        self.clear()
        self.setText("No video loaded")

    def show_first_frame(self, video_path: str) -> np.ndarray | None:
        """Load and display the first frame of a video file. Returns the frame."""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            self.setText("Failed to open video")
            return None
        ret, frame = cap.read()
        cap.release()
        if ret:
            self.update_frame(frame)
            return frame
        self.setText("Failed to read video frame")
        return None
