"""QA Review page for ANPR — Step 4 of the ANPR wizard.

Displays every captured vehicle as a card with vehicle photo, plate photo,
detected plate text, timestamp, direction, and confidence. Allows manual
corrections, AI validation, and grouping by plate text. Feeds corrections
into the ML feedback store for future improvement.
"""

from __future__ import annotations

import logging
import os
from functools import partial

import cv2
import numpy as np

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QFrame,
    QLineEdit,
    QComboBox,
    QGroupBox,
    QSizePolicy,
    QFileDialog,
    QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QImage, QPixmap, QFont

from src.common.theme import (
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_MUTED,
    SUCCESS,
    SUCCESS_LIGHT,
    WARNING,
    WARNING_LIGHT,
    DANGER,
    DANGER_LIGHT,
    BORDER,
    SURFACE_CARD,
    BACK_BUTTON_STYLE,
    NAVY,
    NAVY_LIGHT,
    BG_SECONDARY,
)
from src.common.data_models import VehicleRecord

logger = logging.getLogger(__name__)


# ── Thumbnail helper ────────────────────────────────────────────────


def _load_thumbnail(path: str, max_w: int = 150, max_h: int = 100) -> QPixmap | None:
    """Load an image from disk and return a scaled QPixmap."""
    if not path or not os.path.isfile(path):
        return None
    try:
        img = cv2.imread(path)
        if img is None:
            return None
        h, w = img.shape[:2]
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)
        return pixmap.scaled(
            QSize(max_w, max_h),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    except Exception:
        return None


# ── Confidence color helper ─────────────────────────────────────────


def _confidence_style(confidence: float) -> tuple[str, str, str]:
    """Return (bg_color, text_color, label) for a confidence value."""
    if confidence >= 80.0:
        return SUCCESS_LIGHT, SUCCESS, "HIGH"
    elif confidence >= 60.0:
        return WARNING_LIGHT, WARNING, "MED"
    else:
        return DANGER_LIGHT, DANGER, "LOW"


# ── Vehicle Card Widget ─────────────────────────────────────────────


class VehicleCard(QFrame):
    """Card displaying one vehicle's detection data with edit controls."""

    correction_applied = Signal(str, str, str)  # vehicle_id, old_plate, new_plate
    ai_review_requested = Signal(str)  # vehicle_id
    confirmed = Signal(str)  # vehicle_id

    def __init__(self, vehicle: VehicleRecord, parent=None):
        super().__init__(parent)
        self._vehicle = vehicle
        self._build_ui()

    def _build_ui(self):
        v = self._vehicle
        best = v.best_reading

        # Card styling
        bg, text_col, conf_label = _confidence_style(best.confidence)
        border_col = BORDER
        if v.flagged_for_review:
            border_col = DANGER

        self.setStyleSheet(
            f"VehicleCard {{ background: {SURFACE_CARD}; "
            f"border: 1px solid {border_col}; border-radius: 8px; }}"
        )
        self.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        # ── Vehicle thumbnail ──
        vehicle_thumb = QLabel()
        vehicle_thumb.setFixedSize(150, 100)
        vehicle_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vehicle_thumb.setStyleSheet(
            f"background: {BG_SECONDARY}; border-radius: 4px; border: none;"
        )
        pm = _load_thumbnail(v.vehicle_crop_path, 150, 100)
        if pm:
            vehicle_thumb.setPixmap(pm)
        else:
            vehicle_thumb.setText("No image")
            vehicle_thumb.setStyleSheet(
                f"background: {BG_SECONDARY}; border-radius: 4px; "
                f"color: {TEXT_MUTED}; font-size: 10px; border: none;"
            )
        layout.addWidget(vehicle_thumb)

        # ── Plate thumbnail ──
        plate_thumb = QLabel()
        plate_thumb.setFixedSize(120, 60)
        plate_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plate_thumb.setStyleSheet(
            f"background: {BG_SECONDARY}; border-radius: 4px; border: none;"
        )
        pm2 = _load_thumbnail(best.plate_crop_path, 120, 60)
        if pm2:
            plate_thumb.setPixmap(pm2)
        else:
            plate_thumb.setText("No plate")
            plate_thumb.setStyleSheet(
                f"background: {BG_SECONDARY}; border-radius: 4px; "
                f"color: {TEXT_MUTED}; font-size: 10px; border: none;"
            )
        layout.addWidget(plate_thumb)

        # ── Info column ──
        info_col = QVBoxLayout()
        info_col.setSpacing(4)

        # Plate text + confidence badge
        plate_row = QHBoxLayout()
        plate_row.setSpacing(8)

        plate_text = v.plate_text or "(no reading)"
        plate_lbl = QLabel(plate_text)
        plate_lbl.setFont(QFont("Consolas", 16, QFont.Weight.Bold))
        plate_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; border: none;")
        plate_row.addWidget(plate_lbl)

        # Confidence badge
        conf_badge = QLabel(f"  {best.confidence:.0f}%  {conf_label}  ")
        conf_badge.setStyleSheet(
            f"background: {bg}; color: {text_col}; font-size: 11px; "
            f"font-weight: 600; border-radius: 4px; padding: 2px 6px; border: none;"
        )
        plate_row.addWidget(conf_badge)

        if v.flagged_for_review:
            flag_lbl = QLabel("FLAGGED")
            flag_lbl.setStyleSheet(
                f"background: {DANGER_LIGHT}; color: {DANGER}; font-size: 10px; "
                f"font-weight: 700; border-radius: 3px; padding: 2px 6px; border: none;"
            )
            plate_row.addWidget(flag_lbl)

        if v.user_corrected_plate:
            corrected_lbl = QLabel("CORRECTED")
            corrected_lbl.setStyleSheet(
                f"background: {SUCCESS_LIGHT}; color: {SUCCESS}; font-size: 10px; "
                f"font-weight: 700; border-radius: 3px; padding: 2px 6px; border: none;"
            )
            plate_row.addWidget(corrected_lbl)

        plate_row.addStretch()
        info_col.addLayout(plate_row)

        # Meta row: time, direction, video, ID
        meta_parts = []
        if best.real_time:
            meta_parts.append(f"Time: {best.real_time}")
        if v.direction:
            meta_parts.append(f"Dir: {v.direction}")
        meta_parts.append(f"Video: {os.path.basename(best.video_file)}")
        meta_parts.append(f"ID: {v.vehicle_id}")
        meta_parts.append(f"Readings: {len(v.readings)}")

        meta_lbl = QLabel("  |  ".join(meta_parts))
        meta_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; border: none;")
        info_col.addWidget(meta_lbl)

        # All readings row (show top 3)
        if len(v.readings) > 1:
            readings_strs = []
            for i, r in enumerate(v.readings[:5]):
                tag = "*" if i == v.best_reading_idx else ""
                readings_strs.append(f"{r.plate_text} ({r.confidence:.0f}%){tag}")
            readings_lbl = QLabel("Readings: " + "  |  ".join(readings_strs))
            readings_lbl.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-size: 10px; border: none;"
            )
            info_col.addWidget(readings_lbl)

        layout.addLayout(info_col, stretch=1)

        # ── Action column ──
        action_col = QVBoxLayout()
        action_col.setSpacing(6)

        # Edit field
        edit_row = QHBoxLayout()
        edit_row.setSpacing(4)

        self._edit_field = QLineEdit()
        self._edit_field.setPlaceholderText("Correct plate...")
        self._edit_field.setFixedWidth(110)
        self._edit_field.setStyleSheet("border: 1px solid #D1D5DB; border-radius: 4px; padding: 4px;")
        if v.user_corrected_plate:
            self._edit_field.setText(v.user_corrected_plate)
        edit_row.addWidget(self._edit_field)

        apply_btn = QPushButton("Apply")
        apply_btn.setFixedWidth(50)
        apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_btn.setStyleSheet(
            f"QPushButton {{ background: {NAVY}; color: white; border-radius: 4px; "
            f"padding: 4px 8px; font-size: 11px; border: none; }}"
            f"QPushButton:hover {{ background: #111D35; }}"
        )
        apply_btn.clicked.connect(self._on_apply)
        edit_row.addWidget(apply_btn)

        action_col.addLayout(edit_row)

        # AI review button
        ai_btn = QPushButton("Send to AI")
        ai_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ai_btn.setStyleSheet(
            f"QPushButton {{ background: {WARNING_LIGHT}; color: {WARNING}; "
            f"border: 1px solid {WARNING}; border-radius: 4px; padding: 4px 8px; "
            f"font-size: 11px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: #FEF3C7; }}"
        )
        ai_btn.clicked.connect(lambda: self.ai_review_requested.emit(self._vehicle.vehicle_id))
        action_col.addWidget(ai_btn)

        # Confirm button
        confirm_btn = QPushButton("Confirm")
        confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        confirm_btn.setStyleSheet(
            f"QPushButton {{ background: {SUCCESS_LIGHT}; color: {SUCCESS}; "
            f"border: 1px solid {SUCCESS}; border-radius: 4px; padding: 4px 8px; "
            f"font-size: 11px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: #DCFCE7; }}"
        )
        confirm_btn.clicked.connect(lambda: self.confirmed.emit(self._vehicle.vehicle_id))
        action_col.addWidget(confirm_btn)

        layout.addLayout(action_col)

    def _on_apply(self):
        new_text = self._edit_field.text().strip().upper()
        if not new_text:
            return
        old_plate = self._vehicle.plate_text
        self.correction_applied.emit(self._vehicle.vehicle_id, old_plate, new_text)

    @property
    def vehicle_id(self) -> str:
        return self._vehicle.vehicle_id


# ── QA Review Page ───────────────────────────────────────────────────


class ANPRQAReviewPage(QWidget):
    """Step 4: QA Review of all detected vehicles with correction tools."""

    back_to_processing = Signal()
    export_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._vehicle_store = None
        self._ml_feedback = None
        self._claude_validator = None
        self._cards: list[VehicleCard] = []
        self._filter_mode = "all"
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 20)
        layout.setSpacing(12)

        # ── Top bar: back + summary + filter + export ──
        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)

        back_btn = QPushButton("<  Back to Processing")
        back_btn.setStyleSheet(BACK_BUTTON_STYLE)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self.back_to_processing.emit)
        top_bar.addWidget(back_btn)

        self._summary_label = QLabel("No vehicles loaded")
        self._summary_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 13px; font-weight: 600;"
        )
        top_bar.addWidget(self._summary_label)

        top_bar.addStretch()

        # Filter combo
        filter_lbl = QLabel("Filter:")
        filter_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        top_bar.addWidget(filter_lbl)

        self._filter_combo = QComboBox()
        self._filter_combo.addItems(["All Vehicles", "Flagged Only", "Low Confidence (<60%)", "Corrected"])
        self._filter_combo.setMinimumWidth(160)
        self._filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        top_bar.addWidget(self._filter_combo)

        # Export button
        self._export_btn = QPushButton("Export to Excel")
        self._export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._export_btn.setObjectName("primary_btn")
        self._export_btn.clicked.connect(self._on_export)
        top_bar.addWidget(self._export_btn)

        layout.addLayout(top_bar)

        # ── Stats bar ──
        self._stats_bar = QHBoxLayout()
        self._stats_bar.setSpacing(16)

        self._stat_total = self._make_stat_widget("Total", "0")
        self._stat_flagged = self._make_stat_widget("Flagged", "0")
        self._stat_corrected = self._make_stat_widget("Corrected", "0")
        self._stat_confirmed = self._make_stat_widget("Confirmed", "0")

        self._stats_bar.addWidget(self._stat_total)
        self._stats_bar.addWidget(self._stat_flagged)
        self._stats_bar.addWidget(self._stat_corrected)
        self._stats_bar.addWidget(self._stat_confirmed)
        self._stats_bar.addStretch()

        layout.addLayout(self._stats_bar)

        # ── Scroll area for vehicle cards ──
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._cards_container = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(8)
        self._cards_layout.addStretch()

        self._scroll.setWidget(self._cards_container)
        layout.addWidget(self._scroll, stretch=1)

    @staticmethod
    def _make_stat_widget(label: str, value: str) -> QFrame:
        """Create a small stat chip with label and value."""
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background: {NAVY_LIGHT}; border-radius: 6px; padding: 4px 12px; }}"
        )
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(6)

        val_lbl = QLabel(value)
        val_lbl.setObjectName("stat_value")
        val_lbl.setStyleSheet(
            f"color: {NAVY}; font-size: 16px; font-weight: 700; border: none;"
        )
        lay.addWidget(val_lbl)

        name_lbl = QLabel(label)
        name_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; border: none;"
        )
        lay.addWidget(name_lbl)

        return frame

    def _update_stat(self, widget: QFrame, value: str):
        """Update the value label inside a stat widget."""
        val_lbl = widget.findChild(QLabel, "stat_value")
        if val_lbl:
            val_lbl.setText(value)

    # ── Public API ───────────────────────────────────────────────────

    def set_data(self, vehicle_store, ml_feedback=None, claude_validator=None, job_config=None):
        """Load vehicle data from processing into the QA page.

        Args:
            vehicle_store: VehicleStore with all detected vehicles.
            ml_feedback: Optional MLFeedbackStore for recording corrections.
            claude_validator: Optional ClaudePlateValidator for AI review.
            job_config: Optional JobConfig for export metadata.
        """
        self._vehicle_store = vehicle_store
        self._ml_feedback = ml_feedback
        self._claude_validator = claude_validator
        self._job_config = job_config

        self._refresh_display()

    def _refresh_display(self):
        """Rebuild the card list based on current filter and data."""
        if not self._vehicle_store:
            return

        store = self._vehicle_store

        # Update summary
        self._summary_label.setText(
            f"{store.total_vehicles} vehicles  |  "
            f"{store.total_flagged} flagged  |  "
            f"{store.total_corrected} corrected"
        )

        # Update stats
        self._update_stat(self._stat_total, str(store.total_vehicles))
        self._update_stat(self._stat_flagged, str(store.total_flagged))
        self._update_stat(self._stat_corrected, str(store.total_corrected))

        confirmed = sum(
            1 for v in store.get_all_vehicles()
            if not v.flagged_for_review and not v.user_corrected_plate
            and v.best_reading.confidence >= 70.0
        )
        self._update_stat(self._stat_confirmed, str(confirmed))

        # Get filtered vehicles
        vehicles = self._get_filtered_vehicles()

        # Clear existing cards
        self._clear_cards()

        # Create cards
        for vehicle in vehicles:
            card = VehicleCard(vehicle)
            card.correction_applied.connect(self._on_correction)
            card.ai_review_requested.connect(self._on_ai_review)
            card.confirmed.connect(self._on_confirmed)
            self._cards.append(card)
            # Insert before the stretch
            self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)

    def _get_filtered_vehicles(self) -> list[VehicleRecord]:
        """Return vehicles matching the current filter."""
        if not self._vehicle_store:
            return []

        all_vehicles = self._vehicle_store.get_all_vehicles()
        idx = self._filter_combo.currentIndex()

        if idx == 0:  # All
            return all_vehicles
        elif idx == 1:  # Flagged Only
            return [v for v in all_vehicles if v.flagged_for_review]
        elif idx == 2:  # Low Confidence (<60%)
            return [v for v in all_vehicles if v.best_reading.confidence < 60.0]
        elif idx == 3:  # Corrected
            return [v for v in all_vehicles if v.user_corrected_plate]
        return all_vehicles

    def _clear_cards(self):
        """Remove all vehicle cards from the layout."""
        for card in self._cards:
            self._cards_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

    # ── Filter ───────────────────────────────────────────────────────

    def _on_filter_changed(self, index: int):
        self._refresh_display()

    # ── Corrections ──────────────────────────────────────────────────

    def _on_correction(self, vehicle_id: str, old_plate: str, new_plate: str):
        """Handle a user plate correction."""
        if not self._vehicle_store:
            return

        self._vehicle_store.apply_correction(vehicle_id, new_plate)

        # Record in ML feedback
        if self._ml_feedback and old_plate and new_plate:
            self._ml_feedback.record_correction(old_plate, new_plate)
            self._ml_feedback.save()

        logger.info("User corrected %s: %r -> %r", vehicle_id, old_plate, new_plate)
        self._refresh_display()

    def _on_ai_review(self, vehicle_id: str):
        """Send a vehicle's plate crop to Claude for AI validation."""
        if not self._vehicle_store:
            return
        if not self._claude_validator:
            QMessageBox.information(
                self, "AI Review",
                "Claude validation is not configured.\n\n"
                "Enable it in Setup & Config (Step 2) with your API key."
            )
            return

        vehicle = self._vehicle_store.get_vehicle(vehicle_id)
        if not vehicle:
            return

        best = vehicle.best_reading
        plate_path = best.plate_crop_path

        if not plate_path or not os.path.isfile(plate_path):
            QMessageBox.warning(
                self, "AI Review",
                "No plate image available for this vehicle."
            )
            return

        # Load the plate image
        plate_img = cv2.imread(plate_path)
        if plate_img is None:
            QMessageBox.warning(self, "AI Review", "Could not load plate image.")
            return

        # Call Claude
        try:
            result = self._claude_validator.validate_plate(
                plate_img, best.plate_text, best.confidence / 100.0
            )
        except ImportError as e:
            QMessageBox.warning(self, "AI Review", str(e))
            return
        except Exception as e:
            QMessageBox.warning(self, "AI Review", f"AI validation failed:\n{e}")
            return

        # Apply result
        ai_plate = result.get("plate", "")
        ai_confidence = result.get("confidence", 0.0) * 100.0  # Convert to 0-100

        if ai_plate and ai_plate != "UNREADABLE":
            self._vehicle_store.apply_ai_result(vehicle_id, ai_plate, ai_confidence)

            if result.get("changed"):
                # Record correction for ML feedback
                if self._ml_feedback:
                    self._ml_feedback.record_correction(best.plate_text, ai_plate)
                    self._ml_feedback.save()

            logger.info(
                "AI reviewed %s: %r -> %r (%.0f%%)",
                vehicle_id, best.plate_text, ai_plate, ai_confidence,
            )
        else:
            logger.info("AI could not read plate for %s", vehicle_id)

        self._refresh_display()

    def _on_confirmed(self, vehicle_id: str):
        """Mark a vehicle as confirmed (unflag it)."""
        if not self._vehicle_store:
            return

        vehicle = self._vehicle_store.get_vehicle(vehicle_id)
        if vehicle:
            vehicle.flagged_for_review = False
            logger.info("User confirmed %s", vehicle_id)
            self._refresh_display()

    # ── Export ────────────────────────────────────────────────────────

    def _on_export(self):
        """Export QA-reviewed results to Excel."""
        if not self._vehicle_store or self._vehicle_store.total_vehicles == 0:
            return

        from src.common.survey_widget import SurveyInfo
        from src.anpr.anpr_export import export_anpr_results

        config = getattr(self, "_job_config", None)
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

        # Convert vehicle store to export format
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
            f"ANPR_QA_Report_{site}.xlsx",
            "Excel Files (*.xlsx)",
        )
        if path:
            export_anpr_results(legacy_results, survey, path)
            QMessageBox.information(
                self, "Export Complete",
                f"Exported {len(legacy_results)} vehicles to:\n{path}"
            )
