"""Matrix Traffic and Transport Data — brand theme.

Navy, white, and grey palette derived from the Matrix logo.
Navy (#1B2A4A) for primary accents and headings.
Charcoal grey (#4B5563) for secondary elements and the swoosh.
Clean white backgrounds throughout.
"""

# ── Brand palette (from logo) ──
NAVY = "#1B2A4A"
NAVY_DARK = "#111D35"
NAVY_LIGHT = "#E9EDF3"
NAVY_DIM = "rgba(27, 42, 74, 0.08)"
NAVY_BORDER = "rgba(27, 42, 74, 0.20)"
CHARCOAL = "#4B5563"
CHARCOAL_LIGHT = "#6B7280"

# ── Primary palette ──
BG_PRIMARY = "#FFFFFF"
BG_SECONDARY = "#F7F8FA"
BG_TERTIARY = "#EEF0F4"
ACCENT = NAVY
ACCENT_HOVER = NAVY_DARK
ACCENT_LIGHT = NAVY_LIGHT
ACCENT_DIM = NAVY_DIM
ACCENT_BORDER = NAVY_BORDER

# ── Text ──
TEXT_PRIMARY = "#1A1A2E"
TEXT_SECONDARY = CHARCOAL
TEXT_MUTED = "#9CA3AF"

# ── Borders & surfaces ──
BORDER = "#D1D5DB"
BORDER_HOVER = "#9CA3AF"
BORDER_FOCUS = NAVY
INPUT_BG = "#F7F8FA"
SURFACE_CARD = "#FFFFFF"

# ── Status ──
SUCCESS = "#16A34A"
SUCCESS_LIGHT = "#F0FDF4"
WARNING = "#D97706"
WARNING_LIGHT = "#FFFBEB"
DANGER = "#DC2626"
DANGER_LIGHT = "#FEF2F2"

# ── Derived tokens ──
_CARD_HOVER = "#F1F3F7"
_ROW_ALT = "#FAFBFC"
_SHADOW = "rgba(0, 0, 0, 0.06)"
_SELECTED_BG = "rgba(27, 42, 74, 0.10)"

# ── Legacy aliases (backward compat) ──
DARK_BG = BG_PRIMARY
DARK_SURFACE = BG_SECONDARY
DARK_CARD = SURFACE_CARD

APP_STYLESHEET = f"""
/* ──────────────────── Base ──────────────────── */
QMainWindow {{
    background-color: {BG_PRIMARY};
}}

QWidget {{
    color: {TEXT_PRIMARY};
    font-family: "Segoe UI", "Inter", "SF Pro Display", Arial, sans-serif;
    font-size: 13px;
    outline: none;
}}

QLabel {{
    color: {TEXT_PRIMARY};
    background: transparent;
}}

/* ──────────────────── Inputs ──────────────────── */
QLineEdit {{
    background-color: {INPUT_BG};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 10px 14px;
    color: {TEXT_PRIMARY};
    font-size: 14px;
    selection-background-color: {ACCENT_DIM};
}}

QLineEdit:hover {{
    border-color: {BORDER_HOVER};
}}

QLineEdit:focus {{
    border: 1.5px solid {ACCENT};
    background-color: {BG_PRIMARY};
}}

QLineEdit:disabled {{
    color: {TEXT_MUTED};
    background-color: {BG_TERTIARY};
    border-color: {BORDER};
}}

QLineEdit[echoMode="2"] {{
    lineedit-password-character: 9679;
}}

/* ──────────────────── Buttons ──────────────────── */
QPushButton {{
    background-color: {BG_PRIMARY};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 10px 22px;
    font-size: 13px;
    font-weight: 600;
}}

QPushButton:hover {{
    border-color: {BORDER_HOVER};
    background-color: {BG_SECONDARY};
}}

QPushButton:pressed {{
    background-color: {BG_TERTIARY};
    border-color: {ACCENT};
}}

QPushButton:disabled {{
    background-color: {BG_TERTIARY};
    color: {TEXT_MUTED};
    border-color: {BORDER};
}}

QPushButton#primary_btn {{
    background-color: {NAVY};
    border: 1px solid {NAVY};
    color: #FFFFFF;
}}

QPushButton#primary_btn:hover {{
    background-color: {NAVY_DARK};
    border-color: {NAVY_DARK};
}}

QPushButton#primary_btn:pressed {{
    background-color: #0A1525;
    border-color: #0A1525;
}}

QPushButton#primary_btn:disabled {{
    background-color: {BORDER_HOVER};
    border-color: {BORDER_HOVER};
    color: {BG_PRIMARY};
}}

QPushButton#danger_btn {{
    background-color: {DANGER};
    border: 1px solid {DANGER};
    color: #FFFFFF;
}}

QPushButton#danger_btn:hover {{
    background-color: #B91C1C;
    border-color: #B91C1C;
}}

QPushButton#success_btn {{
    background-color: {SUCCESS};
    border: 1px solid {SUCCESS};
    color: #FFFFFF;
}}

QPushButton#success_btn:hover {{
    background-color: #15803D;
    border-color: #15803D;
}}

/* ──────────────────── Progress Bar ──────────────────── */
QProgressBar {{
    background-color: {BG_TERTIARY};
    border: 1px solid {BORDER};
    border-radius: 8px;
    text-align: center;
    color: {TEXT_PRIMARY};
    height: 26px;
    font-size: 12px;
    font-weight: 600;
}}

QProgressBar::chunk {{
    border-radius: 7px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {NAVY}, stop:1 #2E4A7A);
}}

/* ──────────────────── Tables ──────────────────── */
QTableWidget {{
    background-color: {BG_PRIMARY};
    alternate-background-color: {_ROW_ALT};
    border: 1px solid {BORDER};
    border-radius: 10px;
    gridline-color: {BORDER};
    color: {TEXT_PRIMARY};
    font-size: 12px;
    selection-background-color: {_SELECTED_BG};
    selection-color: {TEXT_PRIMARY};
}}

QTableWidget::item {{
    padding: 8px;
    border: none;
}}

QTableWidget::item:selected {{
    background-color: {_SELECTED_BG};
    color: {TEXT_PRIMARY};
}}

QTableWidget::item:hover {{
    background-color: {_CARD_HOVER};
}}

QHeaderView {{
    background-color: transparent;
}}

QHeaderView::section {{
    background-color: {BG_SECONDARY};
    color: {CHARCOAL};
    padding: 10px 8px;
    border: none;
    border-bottom: 2px solid {BORDER};
    border-right: 1px solid {BORDER};
    font-weight: 700;
    font-size: 11px;
    text-transform: uppercase;
}}

QHeaderView::section:first {{
    border-top-left-radius: 10px;
}}

QHeaderView::section:last {{
    border-top-right-radius: 10px;
    border-right: none;
}}

QHeaderView::section:hover {{
    background-color: {_CARD_HOVER};
    color: {TEXT_PRIMARY};
}}

/* ──────────────────── Checkbox ──────────────────── */
QCheckBox {{
    color: {TEXT_PRIMARY};
    spacing: 10px;
    font-size: 13px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid {BORDER_HOVER};
    border-radius: 5px;
    background-color: {BG_PRIMARY};
}}

QCheckBox::indicator:hover {{
    border-color: {NAVY};
}}

QCheckBox::indicator:checked {{
    background-color: {NAVY};
    border-color: {NAVY};
}}

QCheckBox::indicator:checked:hover {{
    background-color: {NAVY_DARK};
    border-color: {NAVY_DARK};
}}

QCheckBox:disabled {{
    color: {TEXT_MUTED};
}}

QCheckBox::indicator:disabled {{
    background-color: {BG_TERTIARY};
    border-color: {BORDER};
}}

/* ──────────────────── ComboBox ──────────────────── */
QComboBox {{
    background-color: {INPUT_BG};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 10px 14px;
    color: {TEXT_PRIMARY};
    font-size: 13px;
    min-height: 20px;
}}

QComboBox:hover {{
    border-color: {BORDER_HOVER};
}}

QComboBox:focus, QComboBox:on {{
    border-color: {NAVY};
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 30px;
    border-left: 1px solid {BORDER};
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
    background: transparent;
}}

QComboBox::down-arrow {{
    width: 12px;
    height: 12px;
}}

QComboBox QAbstractItemView {{
    background-color: {BG_PRIMARY};
    color: {TEXT_PRIMARY};
    selection-background-color: {_SELECTED_BG};
    selection-color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 4px;
    outline: none;
}}

QComboBox QAbstractItemView::item {{
    padding: 8px 12px;
    border-radius: 4px;
    min-height: 24px;
}}

QComboBox QAbstractItemView::item:hover {{
    background-color: {_CARD_HOVER};
}}

/* ──────────────────── Scrollbars ──────────────────── */
QScrollBar:vertical {{
    background-color: transparent;
    width: 6px;
    margin: 4px 1px;
    border-radius: 3px;
}}

QScrollBar::handle:vertical {{
    background-color: {BORDER_HOVER};
    border-radius: 3px;
    min-height: 40px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {TEXT_MUTED};
}}

QScrollBar::handle:vertical:pressed {{
    background-color: {CHARCOAL};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}

QScrollBar:horizontal {{
    background-color: transparent;
    height: 6px;
    margin: 1px 4px;
    border-radius: 3px;
}}

QScrollBar::handle:horizontal {{
    background-color: {BORDER_HOVER};
    border-radius: 3px;
    min-width: 40px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {TEXT_MUTED};
}}

QScrollBar::handle:horizontal:pressed {{
    background-color: {CHARCOAL};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
}}

/* ──────────────────── GroupBox ──────────────────── */
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 10px;
    margin-top: 16px;
    padding: 24px 12px 12px 12px;
    font-weight: 700;
    font-size: 12px;
    color: {CHARCOAL};
    background-color: {BG_PRIMARY};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 4px 14px;
    color: {CHARCOAL};
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
}}

/* ──────────────────── List Widget ──────────────────── */
QListWidget {{
    background-color: {BG_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 10px;
    color: {TEXT_PRIMARY};
    font-size: 13px;
    padding: 6px;
    outline: none;
}}

QListWidget::item {{
    padding: 8px 12px;
    border-radius: 6px;
    margin: 1px 0px;
}}

QListWidget::item:selected {{
    background-color: {_SELECTED_BG};
    color: {TEXT_PRIMARY};
}}

QListWidget::item:hover {{
    background-color: {_CARD_HOVER};
}}

/* ──────────────────── Time / Date Editors ──────────────────── */
QTimeEdit, QDateEdit {{
    background-color: {INPUT_BG};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 10px 14px;
    color: {TEXT_PRIMARY};
    font-size: 14px;
}}

QTimeEdit:hover, QDateEdit:hover {{
    border-color: {BORDER_HOVER};
}}

QTimeEdit:focus, QDateEdit:focus {{
    border: 1.5px solid {NAVY};
}}

QTimeEdit::up-button, QTimeEdit::down-button,
QDateEdit::up-button, QDateEdit::down-button {{
    background-color: {BG_SECONDARY};
    border: none;
    border-left: 1px solid {BORDER};
    width: 22px;
}}

QTimeEdit::up-button:hover, QTimeEdit::down-button:hover,
QDateEdit::up-button:hover, QDateEdit::down-button:hover {{
    background-color: {_CARD_HOVER};
}}

QDateEdit::drop-down {{
    background-color: transparent;
    border: none;
    border-left: 1px solid {BORDER};
    width: 26px;
}}

QDateEdit::drop-down:hover {{
    background-color: {_CARD_HOVER};
}}

/* ──────────────────── Calendar Popup ──────────────────── */
QCalendarWidget {{
    background-color: {BG_PRIMARY};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}

QCalendarWidget QAbstractItemView {{
    background-color: {BG_PRIMARY};
    color: {TEXT_PRIMARY};
    selection-background-color: {NAVY};
    selection-color: #FFFFFF;
    alternate-background-color: {_ROW_ALT};
    font-size: 12px;
    outline: none;
}}

QCalendarWidget QWidget {{
    color: {TEXT_PRIMARY};
}}

QCalendarWidget QToolButton {{
    color: {TEXT_PRIMARY};
    background-color: {BG_SECONDARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 10px;
    font-weight: 600;
}}

QCalendarWidget QToolButton:hover {{
    border-color: {NAVY};
    background-color: {_CARD_HOVER};
}}

QCalendarWidget QSpinBox {{
    background-color: {INPUT_BG};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px 8px;
}}

QCalendarWidget QMenu {{
    background-color: {BG_PRIMARY};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
}}

QCalendarWidget QMenu::item:selected {{
    background-color: {_SELECTED_BG};
}}

QCalendarWidget #qt_calendar_navigationbar {{
    background-color: {BG_SECONDARY};
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    padding: 4px;
}}

/* ──────────────────── Spin Boxes ──────────────────── */
QDoubleSpinBox, QSpinBox {{
    background-color: {INPUT_BG};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 10px 14px;
    color: {TEXT_PRIMARY};
    font-size: 14px;
}}

QDoubleSpinBox:hover, QSpinBox:hover {{
    border-color: {BORDER_HOVER};
}}

QDoubleSpinBox:focus, QSpinBox:focus {{
    border: 1.5px solid {NAVY};
}}

QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
QSpinBox::up-button, QSpinBox::down-button {{
    background-color: {BG_SECONDARY};
    border: none;
    border-left: 1px solid {BORDER};
    width: 22px;
}}

QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover,
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background-color: {_CARD_HOVER};
}}

/* ──────────────────── Tree Widget ──────────────────── */
QTreeWidget {{
    background-color: {BG_PRIMARY};
    alternate-background-color: {_ROW_ALT};
    border: 1px solid {BORDER};
    border-radius: 10px;
    color: {TEXT_PRIMARY};
    font-size: 13px;
    padding: 6px;
    outline: none;
}}

QTreeWidget::item {{
    padding: 6px 10px;
    border-radius: 4px;
}}

QTreeWidget::item:selected {{
    background-color: {_SELECTED_BG};
    color: {TEXT_PRIMARY};
}}

QTreeWidget::item:hover {{
    background-color: {_CARD_HOVER};
}}

QTreeWidget::branch {{
    background: transparent;
}}

QTreeWidget::branch:selected {{
    background-color: {_SELECTED_BG};
}}

QTreeWidget QHeaderView::section {{
    background-color: {BG_SECONDARY};
    color: {CHARCOAL};
    padding: 8px;
    border: none;
    border-bottom: 2px solid {BORDER};
    border-right: 1px solid {BORDER};
    font-weight: 700;
    font-size: 11px;
    text-transform: uppercase;
}}

/* ──────────────────── Scroll Area ──────────────────── */
QScrollArea {{
    border: none;
    background: transparent;
}}

QScrollArea > QWidget > QWidget {{
    background: transparent;
}}

/* ──────────────────── Tab Widget ──────────────────── */
QTabWidget {{
    border: none;
    background: transparent;
}}

QTabWidget::pane {{
    background-color: {BG_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 10px;
    top: -1px;
    padding: 8px;
}}

QTabBar {{
    background: transparent;
}}

QTabBar::tab {{
    background-color: transparent;
    color: {CHARCOAL};
    padding: 10px 20px;
    margin-right: 2px;
    border: none;
    border-bottom: 2px solid transparent;
    font-weight: 600;
    font-size: 13px;
}}

QTabBar::tab:hover {{
    color: {TEXT_PRIMARY};
    border-bottom-color: {BORDER_HOVER};
}}

QTabBar::tab:selected {{
    color: {NAVY};
    border-bottom-color: {NAVY};
}}

/* ──────────────────── Tooltips ──────────────────── */
QToolTip {{
    background-color: {NAVY};
    color: {BG_PRIMARY};
    border: 1px solid {NAVY_DARK};
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 12px;
}}

/* ──────────────────── Menu ──────────────────── */
QMenu {{
    background-color: {BG_PRIMARY};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px;
}}

QMenu::item {{
    padding: 8px 24px 8px 12px;
    border-radius: 4px;
}}

QMenu::item:selected {{
    background-color: {_SELECTED_BG};
}}

QMenu::separator {{
    height: 1px;
    background-color: {BORDER};
    margin: 4px 8px;
}}

/* ──────────────────── Status Bar ──────────────────── */
QStatusBar {{
    background-color: {BG_SECONDARY};
    color: {CHARCOAL};
    border-top: 1px solid {BORDER};
    font-size: 12px;
}}

/* ──────────────────── Splitter ──────────────────── */
QSplitter::handle {{
    background-color: {BORDER};
}}

QSplitter::handle:horizontal {{
    width: 1px;
}}

QSplitter::handle:vertical {{
    height: 1px;
}}

QSplitter::handle:hover {{
    background-color: {NAVY};
}}

/* ──────────────────── Slider ──────────────────── */
QSlider::groove:horizontal {{
    border: none;
    height: 4px;
    background-color: {BORDER};
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background-color: {NAVY};
    border: none;
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}}

QSlider::handle:horizontal:hover {{
    background-color: {NAVY_DARK};
}}

QSlider::sub-page:horizontal {{
    background-color: {NAVY};
    border-radius: 2px;
}}

/* ──────────────────── Text Edit ──────────────────── */
QTextEdit, QPlainTextEdit {{
    background-color: {INPUT_BG};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 10px;
    color: {TEXT_PRIMARY};
    font-size: 13px;
    selection-background-color: {ACCENT_DIM};
}}

QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1.5px solid {NAVY};
}}

/* ──────────────────── Radio Button ──────────────────── */
QRadioButton {{
    color: {TEXT_PRIMARY};
    spacing: 10px;
    font-size: 13px;
}}

QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid {BORDER_HOVER};
    border-radius: 10px;
    background-color: {BG_PRIMARY};
}}

QRadioButton::indicator:hover {{
    border-color: {NAVY};
}}

QRadioButton::indicator:checked {{
    background-color: {NAVY};
    border-color: {NAVY};
}}
"""

# ── Card style for landing page module cards ──
CARD_STYLE = f"""
QPushButton {{
    background-color: {BG_PRIMARY};
    border: 1.5px solid {CHARCOAL};
    border-bottom: 2.5px solid {CHARCOAL};
    border-radius: 12px;
    padding: 36px 28px;
    text-align: center;
    font-size: 14px;
    font-weight: 600;
    color: {NAVY};
    min-width: 280px;
    min-height: 180px;
}}

QPushButton:hover {{
    border: 2px solid {NAVY};
    border-bottom: 3px solid {NAVY};
    background-color: {NAVY_LIGHT};
}}

QPushButton:pressed {{
    border: 2px solid {NAVY_DARK};
    border-bottom: 3px solid {NAVY_DARK};
    background-color: {_SELECTED_BG};
}}
"""

# ── Back button style (transparent, text-only) ──
BACK_BUTTON_STYLE = f"""
QPushButton {{
    background-color: transparent;
    border: none;
    color: {CHARCOAL};
    font-size: 14px;
    font-weight: 500;
    padding: 8px 16px;
    text-align: left;
}}

QPushButton:hover {{
    color: {NAVY};
    background-color: transparent;
}}

QPushButton:pressed {{
    color: {NAVY_DARK};
}}
"""

# ── Wizard step indicator styles ──
STEP_ACTIVE = f"""
QLabel {{
    color: {NAVY};
    font-weight: 700;
    font-size: 14px;
}}
"""

STEP_INACTIVE = f"""
QLabel {{
    color: {TEXT_MUTED};
    font-weight: 500;
    font-size: 14px;
}}
"""

STEP_COMPLETED = f"""
QLabel {{
    color: {SUCCESS};
    font-weight: 600;
    font-size: 14px;
}}
"""

# ── Section header style ──
SECTION_HEADER = f"""
QLabel {{
    color: {NAVY};
    font-weight: 700;
    font-size: 16px;
    padding: 4px 0px;
}}
"""

# ── Info banner (light navy background) ──
INFO_BANNER = f"""
QFrame {{
    background-color: {NAVY_LIGHT};
    border: 1px solid {NAVY_BORDER};
    border-radius: 8px;
    padding: 12px 16px;
}}

QFrame QLabel {{
    color: {NAVY};
    font-size: 13px;
}}
"""

# ── Status badge styles ──
STATUS_SUCCESS = f"""
QLabel {{
    background-color: {SUCCESS_LIGHT};
    color: {SUCCESS};
    border: 1px solid {SUCCESS};
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}}
"""

STATUS_WARNING = f"""
QLabel {{
    background-color: {WARNING_LIGHT};
    color: {WARNING};
    border: 1px solid {WARNING};
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}}
"""

STATUS_DANGER = f"""
QLabel {{
    background-color: {DANGER_LIGHT};
    color: {DANGER};
    border: 1px solid {DANGER};
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}}
"""
