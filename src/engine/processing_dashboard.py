"""PySide6 widget for multi-stream processing progress display.

Shows a grid of per-stream cards with progress bars, status text,
counts, and optional live preview thumbnails, plus a master progress
bar and Start/Stop controls.
"""

from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.common.theme import (
    ACCENT,
    BG_PRIMARY,
    BG_SECONDARY,
    BORDER,
    DANGER,
    SUCCESS,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


# ── Per-stream card widget ────────────────────────────────────────────


class StreamCard(QFrame):
    """A card displaying progress information for a single processing stream."""

    def __init__(self, stream_id: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.stream_id = stream_id
        self._vehicle_count = 0
        self._plate_count = 0

        self._build_ui()
        self._apply_style()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Stream header
        self._header_label = QLabel(f"Stream {self.stream_id + 1}")
        self._header_label.setStyleSheet(
            f"font-weight: 700; font-size: 14px; color: {TEXT_PRIMARY};"
        )
        layout.addWidget(self._header_label)

        # Current video filename
        self._video_label = QLabel("Waiting...")
        self._video_label.setStyleSheet(
            f"font-size: 12px; color: {TEXT_SECONDARY};"
        )
        self._video_label.setWordWrap(True)
        layout.addWidget(self._video_label)

        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFixedHeight(22)
        layout.addWidget(self._progress_bar)

        # Counts label
        self._counts_label = QLabel("Vehicles: 0  |  Plates: 0")
        self._counts_label.setStyleSheet(
            f"font-size: 12px; color: {TEXT_SECONDARY};"
        )
        layout.addWidget(self._counts_label)

        # Preview frame label (hidden by default)
        self._preview_label = QLabel()
        self._preview_label.setFixedSize(320, 180)
        self._preview_label.setAlignment(Qt.AlignCenter)
        self._preview_label.setStyleSheet(
            f"background-color: {BG_SECONDARY}; border: 1px solid {BORDER}; "
            f"border-radius: 6px;"
        )
        self._preview_label.setVisible(False)
        layout.addWidget(self._preview_label)

        # Status label
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(
            f"font-size: 11px; color: {TEXT_MUTED};"
        )
        layout.addWidget(self._status_label)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            f"StreamCard {{"
            f"  background-color: {BG_PRIMARY};"
            f"  border: 1px solid {BORDER};"
            f"  border-radius: 10px;"
            f"}}"
        )

    # ── Public update methods ─────────────────────────────────────────

    def set_video_name(self, filename: str) -> None:
        self._video_label.setText(filename)

    def set_progress(self, percent: int) -> None:
        self._progress_bar.setValue(min(max(percent, 0), 100))

    def set_status(self, text: str) -> None:
        self._status_label.setText(text)

    def set_preview_frame(self, qimage: QImage) -> None:
        if self._preview_label.isVisible():
            pixmap = QPixmap.fromImage(qimage).scaled(
                self._preview_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self._preview_label.setPixmap(pixmap)

    def set_preview_visible(self, visible: bool) -> None:
        self._preview_label.setVisible(visible)

    def increment_vehicle(self) -> None:
        self._vehicle_count += 1
        self._update_counts()

    def increment_plate(self) -> None:
        self._plate_count += 1
        self._update_counts()

    def update_counts(self, vehicles: int, plates: int) -> None:
        self._vehicle_count = vehicles
        self._plate_count = plates
        self._update_counts()

    def mark_finished(self) -> None:
        self._progress_bar.setValue(100)
        self._status_label.setText("Completed")
        self._status_label.setStyleSheet(
            f"font-size: 11px; color: {SUCCESS}; font-weight: 600;"
        )

    def mark_error(self, message: str) -> None:
        self._status_label.setText(f"Error: {message}")
        self._status_label.setStyleSheet(
            f"font-size: 11px; color: {DANGER}; font-weight: 600;"
        )

    def _update_counts(self) -> None:
        self._counts_label.setText(
            f"Vehicles: {self._vehicle_count}  |  Plates: {self._plate_count}"
        )


# ── Main dashboard widget ─────────────────────────────────────────────


class ProcessingDashboard(QWidget):
    """Multi-stream processing progress dashboard.

    Displays a grid of StreamCard widgets, a master progress bar,
    and Start/Stop controls.

    Signals:
        start_requested: Emitted when the user clicks Start.
        stop_requested:  Emitted when the user clicks Stop.
    """

    start_requested = Signal()
    stop_requested = Signal()

    def __init__(
        self,
        num_streams: int = 1,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._num_streams = num_streams
        self._cards: dict[int, StreamCard] = {}
        self._previews_visible = False

        self._build_ui()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        # ── Master progress section ───────────────────────────────────
        master_frame = QFrame()
        master_frame.setStyleSheet(
            f"QFrame {{"
            f"  background-color: {BG_PRIMARY};"
            f"  border: 1px solid {BORDER};"
            f"  border-radius: 10px;"
            f"}}"
        )
        master_layout = QVBoxLayout(master_frame)
        master_layout.setContentsMargins(16, 12, 16, 12)
        master_layout.setSpacing(8)

        header_row = QHBoxLayout()
        title = QLabel("Overall Progress")
        title.setStyleSheet(
            f"font-weight: 700; font-size: 15px; color: {TEXT_PRIMARY}; border: none;"
        )
        header_row.addWidget(title)
        header_row.addStretch()

        self._master_percent_label = QLabel("0%")
        self._master_percent_label.setStyleSheet(
            f"font-weight: 700; font-size: 14px; color: {ACCENT}; border: none;"
        )
        header_row.addWidget(self._master_percent_label)
        master_layout.addLayout(header_row)

        self._master_progress = QProgressBar()
        self._master_progress.setRange(0, 100)
        self._master_progress.setValue(0)
        self._master_progress.setTextVisible(False)
        self._master_progress.setFixedHeight(12)
        self._master_progress.setStyleSheet(
            f"QProgressBar {{"
            f"  background-color: {BG_SECONDARY};"
            f"  border: none;"
            f"  border-radius: 6px;"
            f"}}"
            f"QProgressBar::chunk {{"
            f"  background-color: {ACCENT};"
            f"  border-radius: 6px;"
            f"}}"
        )
        master_layout.addWidget(self._master_progress)

        root_layout.addWidget(master_frame)

        # ── Button row ────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._start_btn = QPushButton("Start Processing")
        self._start_btn.setObjectName("primary_btn")
        self._start_btn.setFixedHeight(40)
        self._start_btn.setCursor(Qt.PointingHandCursor)
        self._start_btn.clicked.connect(self.start_requested.emit)
        btn_row.addWidget(self._start_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setObjectName("danger_btn")
        self._stop_btn.setFixedHeight(40)
        self._stop_btn.setCursor(Qt.PointingHandCursor)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self.stop_requested.emit)
        btn_row.addWidget(self._stop_btn)

        btn_row.addStretch()
        root_layout.addLayout(btn_row)

        # ── Stream cards grid (inside scroll area) ────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        grid_container = QWidget()
        grid_container.setStyleSheet("background: transparent;")
        self._grid_layout = QGridLayout(grid_container)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(12)

        # Determine columns (2 if many streams, else 1)
        cols = 2 if self._num_streams > 2 else 1

        for i in range(self._num_streams):
            card = StreamCard(stream_id=i)
            row = i // cols
            col = i % cols
            self._grid_layout.addWidget(card, row, col)
            self._cards[i] = card

        scroll.setWidget(grid_container)
        root_layout.addWidget(scroll, stretch=1)

    # ── Public update slots ───────────────────────────────────────────

    def update_stream_progress(self, stream_id: int, percent: int) -> None:
        """Update a single stream's progress bar and recalculate master."""
        card = self._cards.get(stream_id)
        if card:
            card.set_progress(percent)
        self._recalc_master()

    def update_stream_frame(self, stream_id: int, qimage: QImage) -> None:
        """Update a stream's preview thumbnail."""
        card = self._cards.get(stream_id)
        if card:
            card.set_preview_frame(qimage)

    def update_stream_status(self, stream_id: int, text: str) -> None:
        """Update a stream's status text."""
        card = self._cards.get(stream_id)
        if card:
            card.set_status(text)

    def update_stream_video(self, stream_id: int, filename: str) -> None:
        """Update the current video filename shown on a stream card."""
        card = self._cards.get(stream_id)
        if card:
            card.set_video_name(filename)

    def mark_stream_finished(self, stream_id: int, results: dict) -> None:
        """Mark a stream as completed."""
        card = self._cards.get(stream_id)
        if card:
            vehicles = results.get("vehicle_count", 0)
            plates = results.get("plate_count", 0)
            card.update_counts(vehicles, plates)
            card.mark_finished()
        self._recalc_master()

    def mark_stream_error(self, stream_id: int, message: str) -> None:
        """Mark a stream as errored."""
        card = self._cards.get(stream_id)
        if card:
            card.mark_error(message)

    def mark_all_finished(self) -> None:
        """Called when all streams are done — update master bar and buttons."""
        self._master_progress.setValue(100)
        self._master_percent_label.setText("100%")
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)

    def set_running_state(self, running: bool) -> None:
        """Toggle button enabled states for running/stopped."""
        self._start_btn.setEnabled(not running)
        self._stop_btn.setEnabled(running)

    def toggle_previews(self, visible: bool) -> None:
        """Show or hide preview thumbnails on all stream cards."""
        self._previews_visible = visible
        for card in self._cards.values():
            card.set_preview_visible(visible)

    # ── Internal helpers ──────────────────────────────────────────────

    def _recalc_master(self) -> None:
        """Recalculate the master progress bar from individual cards."""
        if not self._cards:
            return
        total = sum(
            card._progress_bar.value() for card in self._cards.values()
        )
        avg = total // len(self._cards)
        self._master_progress.setValue(avg)
        self._master_percent_label.setText(f"{avg}%")
