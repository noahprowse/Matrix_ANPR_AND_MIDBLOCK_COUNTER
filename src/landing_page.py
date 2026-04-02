"""Matrix branded landing page with module selection cards.

Navy/white/grey theme matching the Matrix Traffic and Transport Data logo.
4 module cards: ANPR, Midblock Counter, Intersection Counter, and Pedestrian Counter.
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpacerItem,
    QSizePolicy,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont, QPixmap, QColor

from src.common.theme import (
    CARD_STYLE,
    BG_PRIMARY,
    BG_SECONDARY,
    NAVY,
    NAVY_DARK,
    NAVY_LIGHT,
    CHARCOAL,
    CHARCOAL_LIGHT,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_MUTED,
    BORDER,
)


# ── Resolve logo path ──
_LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "matrix-logo.png"


class ModuleCard(QPushButton):
    """Clickable card for module selection on the landing page.

    Each card has a structured layout: icon badge, title, and description
    arranged vertically with clear visual hierarchy.
    """

    def __init__(
        self, icon_text: str, title: str, description: str, parent=None
    ):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(CARD_STYLE)

        # Build structured label with distinct visual sections
        # Icon badge in navy, title bold, description in lighter weight
        label_text = f"{icon_text}\n\n{title}\n\n{description}"
        self.setText(label_text)

        # Add subtle drop shadow for depth
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 25))
        self.setGraphicsEffect(shadow)


class LandingPage(QWidget):
    """Landing page with Matrix branding, 3 module cards, and settings access."""

    module_selected = Signal(str)  # "anpr", "counter", "intersection", or "settings"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {BG_PRIMARY};")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(60, 24, 60, 32)
        layout.setSpacing(0)

        # ── Top bar with settings gear button ──
        top_bar = QHBoxLayout()
        top_bar.addStretch()

        settings_btn = QPushButton("\u2699")  # gear unicode
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.setToolTip("Settings")
        settings_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1.5px solid {CHARCOAL};
                border-radius: 20px;
                color: {CHARCOAL};
                font-size: 22px;
                padding: 0px;
                min-width: 40px;
                max-width: 40px;
                min-height: 40px;
                max-height: 40px;
            }}
            QPushButton:hover {{
                border-color: {NAVY};
                color: {NAVY};
                background-color: {NAVY_LIGHT};
            }}
            QPushButton:pressed {{
                color: {NAVY_DARK};
                background-color: {BG_SECONDARY};
            }}
        """)
        settings_btn.clicked.connect(lambda: self.module_selected.emit("settings"))
        top_bar.addWidget(settings_btn)
        layout.addLayout(top_bar)

        # ── Top spacer ──
        layout.addSpacerItem(
            QSpacerItem(20, 24, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        )

        # ── Logo image ──
        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_label.setStyleSheet("background: transparent;")

        if _LOGO_PATH.exists():
            pixmap = QPixmap(str(_LOGO_PATH))
            # Scale to 400px wide, keep aspect ratio, smooth transform
            scaled = pixmap.scaledToWidth(
                400, Qt.TransformationMode.SmoothTransformation
            )
            logo_label.setPixmap(scaled)
        else:
            # Fallback: text logo if image not found
            logo_label.setText("MATRIX")
            logo_font = QFont("Segoe UI", 52, QFont.Weight.Bold)
            logo_label.setFont(logo_font)
            logo_label.setStyleSheet(f"""
                color: {NAVY};
                letter-spacing: 14px;
                padding: 10px;
                background: transparent;
            """)

        layout.addWidget(logo_label)
        layout.addSpacing(20)

        # ── Tagline ──
        tagline = QLabel("AI-Powered ANPR, Classification, Intersection & Pedestrian Analysis")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline_font = QFont("Segoe UI", 11)
        tagline_font.setItalic(True)
        tagline.setFont(tagline_font)
        tagline.setStyleSheet(f"color: {CHARCOAL_LIGHT}; margin-bottom: 6px;")
        layout.addWidget(tagline)

        layout.addSpacing(28)

        # ── Instruction ──
        instruction = QLabel("Select a module to begin")
        instruction.setAlignment(Qt.AlignmentFlag.AlignCenter)
        instruction_font = QFont("Segoe UI", 13)
        instruction_font.setWeight(QFont.Weight.Medium)
        instruction.setFont(instruction_font)
        instruction.setStyleSheet(
            f"color: {CHARCOAL}; font-size: 15px; margin-bottom: 8px;"
        )
        layout.addWidget(instruction)

        layout.addSpacing(16)

        # ── Cards row — 3 cards ──
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(32)
        cards_layout.addStretch()

        # ANPR Card
        anpr_card = ModuleCard(
            icon_text="\U0001F50D  ANPR",
            title="ANPR Data Extraction",
            description="Detect and extract number plates\nfrom video with frame-accurate timestamps",
        )
        anpr_card.clicked.connect(lambda: self.module_selected.emit("anpr"))
        cards_layout.addWidget(anpr_card)

        # Midblock Counter Card
        counter_card = ModuleCard(
            icon_text="\U0001F4CA  COUNT",
            title="Midblock Vehicle Counter",
            description="Count and classify vehicles crossing\na virtual count line in real time",
        )
        counter_card.clicked.connect(lambda: self.module_selected.emit("counter"))
        cards_layout.addWidget(counter_card)

        # Intersection Counter Card
        intersection_card = ModuleCard(
            icon_text="\U0001F504  TMC",
            title="Intersection Counter",
            description="Zone-based turning movement counts\nand origin-destination analysis",
        )
        intersection_card.clicked.connect(
            lambda: self.module_selected.emit("intersection")
        )
        cards_layout.addWidget(intersection_card)

        # Pedestrian Counter Card
        pedestrian_card = ModuleCard(
            icon_text="\U0001F6B6  PED",
            title="Pedestrian Counter",
            description="Count pedestrians crossing\na virtual count line in real time",
        )
        pedestrian_card.clicked.connect(
            lambda: self.module_selected.emit("pedestrian")
        )
        cards_layout.addWidget(pedestrian_card)

        cards_layout.addStretch()
        layout.addLayout(cards_layout)

        # ── Bottom spacer ──
        layout.addSpacerItem(
            QSpacerItem(20, 32, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        )

        # ── Version label ──
        version = QLabel("v3.0.0")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setStyleSheet(f"color: {NAVY}; font-size: 11px; font-weight: 500;")
        layout.addWidget(version)
