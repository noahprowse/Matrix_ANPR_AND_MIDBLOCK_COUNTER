"""Matrix Traffic brand colors and application stylesheet.

Modern dark-mode professional theme inspired by Linear, Figma, and Vercel.
"""

# Brand colors
DARK_BG = "#0f0f13"
DARK_SURFACE = "#1a1a24"
DARK_CARD = "#22222e"
ACCENT = "#00d4aa"
ACCENT_HOVER = "#00f5c8"
DANGER = "#ff4757"
TEXT_PRIMARY = "#f0f0f5"
TEXT_SECONDARY = "#8888a0"
TEXT_MUTED = "#555566"
SUCCESS = "#00d68f"
WARNING = "#ffa502"
BORDER = "#2a2a38"
INPUT_BG = "#15151f"

# Derived palette tokens
_CARD_HOVER = "#2a2a3a"
_ROW_ALT = "#1e1e2a"
_SHADOW = "rgba(0, 0, 0, 0.35)"
_ACCENT_DIM = "rgba(0, 212, 170, 0.12)"
_ACCENT_BORDER = "rgba(0, 212, 170, 0.30)"

APP_STYLESHEET = f"""
/* ──────────────────── Base ──────────────────── */
QMainWindow {{
    background-color: {DARK_BG};
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
    selection-background-color: {_ACCENT_DIM};
}}

QLineEdit:hover {{
    border-color: {TEXT_MUTED};
}}

QLineEdit:focus {{
    border: 1px solid {ACCENT};
    background-color: {DARK_BG};
}}

QLineEdit:disabled {{
    color: {TEXT_MUTED};
    background-color: {DARK_SURFACE};
    border-color: {BORDER};
}}

/* ──────────────────── Buttons ──────────────────── */
QPushButton {{
    background-color: transparent;
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 10px 22px;
    font-size: 13px;
    font-weight: 600;
}}

QPushButton:hover {{
    border-color: {TEXT_MUTED};
    background-color: {DARK_CARD};
}}

QPushButton:pressed {{
    background-color: {DARK_SURFACE};
    border-color: {ACCENT};
}}

QPushButton:disabled {{
    background-color: {DARK_SURFACE};
    color: {TEXT_MUTED};
    border-color: {BORDER};
}}

QPushButton#primary_btn {{
    background-color: {ACCENT};
    border: 1px solid {ACCENT};
    color: {DARK_BG};
}}

QPushButton#primary_btn:hover {{
    background-color: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}

QPushButton#primary_btn:pressed {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}

QPushButton#primary_btn:disabled {{
    background-color: {TEXT_MUTED};
    border-color: {TEXT_MUTED};
    color: {DARK_BG};
}}

/* ──────────────────── Progress Bar ──────────────────── */
QProgressBar {{
    background-color: {INPUT_BG};
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
        stop:0 {ACCENT}, stop:1 {ACCENT_HOVER});
}}

/* ──────────────────── Tables ──────────────────── */
QTableWidget {{
    background-color: {DARK_SURFACE};
    alternate-background-color: {_ROW_ALT};
    border: 1px solid {BORDER};
    border-radius: 10px;
    gridline-color: {BORDER};
    color: {TEXT_PRIMARY};
    font-size: 12px;
    selection-background-color: {_ACCENT_DIM};
    selection-color: {TEXT_PRIMARY};
}}

QTableWidget::item {{
    padding: 8px;
    border: none;
}}

QTableWidget::item:selected {{
    background-color: {_ACCENT_DIM};
    color: {TEXT_PRIMARY};
}}

QTableWidget::item:hover {{
    background-color: {DARK_CARD};
}}

QHeaderView {{
    background-color: transparent;
}}

QHeaderView::section {{
    background-color: {DARK_CARD};
    color: {TEXT_SECONDARY};
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
    border: 2px solid {BORDER};
    border-radius: 5px;
    background-color: {INPUT_BG};
}}

QCheckBox::indicator:hover {{
    border-color: {TEXT_MUTED};
}}

QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}

QCheckBox::indicator:checked:hover {{
    background-color: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}

QCheckBox:disabled {{
    color: {TEXT_MUTED};
}}

QCheckBox::indicator:disabled {{
    background-color: {DARK_SURFACE};
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
    border-color: {TEXT_MUTED};
}}

QComboBox:focus, QComboBox:on {{
    border-color: {ACCENT};
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
    background-color: {DARK_SURFACE};
    color: {TEXT_PRIMARY};
    selection-background-color: {_ACCENT_DIM};
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
    background-color: {DARK_CARD};
}}

/* ──────────────────── Scrollbars ──────────────────── */
QScrollBar:vertical {{
    background-color: transparent;
    width: 6px;
    margin: 4px 1px;
    border-radius: 3px;
}}

QScrollBar::handle:vertical {{
    background-color: {BORDER};
    border-radius: 3px;
    min-height: 40px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {TEXT_MUTED};
}}

QScrollBar::handle:vertical:pressed {{
    background-color: {TEXT_SECONDARY};
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
    background-color: {BORDER};
    border-radius: 3px;
    min-width: 40px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {TEXT_MUTED};
}}

QScrollBar::handle:horizontal:pressed {{
    background-color: {TEXT_SECONDARY};
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
    color: {TEXT_SECONDARY};
    background-color: {DARK_SURFACE};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 4px 14px;
    color: {TEXT_SECONDARY};
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
}}

/* ──────────────────── List Widget ──────────────────── */
QListWidget {{
    background-color: {INPUT_BG};
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
    background-color: {_ACCENT_DIM};
    color: {TEXT_PRIMARY};
}}

QListWidget::item:hover {{
    background-color: {DARK_CARD};
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
    border-color: {TEXT_MUTED};
}}

QTimeEdit:focus, QDateEdit:focus {{
    border: 1px solid {ACCENT};
}}

QTimeEdit::up-button, QTimeEdit::down-button,
QDateEdit::up-button, QDateEdit::down-button {{
    background-color: {DARK_CARD};
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
    background-color: {DARK_CARD};
}}

/* ──────────────────── Calendar Popup ──────────────────── */
QCalendarWidget {{
    background-color: {DARK_SURFACE};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}

QCalendarWidget QAbstractItemView {{
    background-color: {DARK_SURFACE};
    color: {TEXT_PRIMARY};
    selection-background-color: {ACCENT};
    selection-color: {DARK_BG};
    alternate-background-color: {_ROW_ALT};
    font-size: 12px;
    outline: none;
}}

QCalendarWidget QWidget {{
    color: {TEXT_PRIMARY};
}}

QCalendarWidget QToolButton {{
    color: {TEXT_PRIMARY};
    background-color: {DARK_CARD};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 10px;
    font-weight: 600;
}}

QCalendarWidget QToolButton:hover {{
    border-color: {ACCENT};
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
    background-color: {DARK_SURFACE};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
}}

QCalendarWidget QMenu::item:selected {{
    background-color: {_ACCENT_DIM};
}}

QCalendarWidget #qt_calendar_navigationbar {{
    background-color: {DARK_CARD};
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
    border-color: {TEXT_MUTED};
}}

QDoubleSpinBox:focus, QSpinBox:focus {{
    border: 1px solid {ACCENT};
}}

QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
QSpinBox::up-button, QSpinBox::down-button {{
    background-color: {DARK_CARD};
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
    background-color: {INPUT_BG};
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
    background-color: {_ACCENT_DIM};
    color: {TEXT_PRIMARY};
}}

QTreeWidget::item:hover {{
    background-color: {DARK_CARD};
}}

QTreeWidget::branch {{
    background: transparent;
}}

QTreeWidget::branch:selected {{
    background-color: {_ACCENT_DIM};
}}

QTreeWidget QHeaderView::section {{
    background-color: {DARK_CARD};
    color: {TEXT_SECONDARY};
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
    background-color: {DARK_SURFACE};
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
    color: {TEXT_SECONDARY};
    padding: 10px 20px;
    margin-right: 2px;
    border: none;
    border-bottom: 2px solid transparent;
    font-weight: 600;
    font-size: 13px;
}}

QTabBar::tab:hover {{
    color: {TEXT_PRIMARY};
    border-bottom-color: {TEXT_MUTED};
}}

QTabBar::tab:selected {{
    color: {ACCENT};
    border-bottom-color: {ACCENT};
}}

/* ──────────────────── Tooltips ──────────────────── */
QToolTip {{
    background-color: {DARK_CARD};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 12px;
}}

/* ──────────────────── Menu ──────────────────── */
QMenu {{
    background-color: {DARK_SURFACE};
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
    background-color: {_ACCENT_DIM};
}}

QMenu::separator {{
    height: 1px;
    background-color: {BORDER};
    margin: 4px 8px;
}}

/* ──────────────────── Status Bar ──────────────────── */
QStatusBar {{
    background-color: {DARK_BG};
    color: {TEXT_SECONDARY};
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
    background-color: {ACCENT};
}}
"""

CARD_STYLE = f"""
QPushButton {{
    background-color: {DARK_CARD};
    border: 1px solid {BORDER};
    border-radius: 14px;
    padding: 44px;
    text-align: center;
    font-size: 18px;
    font-weight: 700;
    color: {TEXT_PRIMARY};
    min-width: 300px;
    min-height: 200px;
}}

QPushButton:hover {{
    border-color: {ACCENT};
    background-color: {_CARD_HOVER};
}}

QPushButton:pressed {{
    border-color: {ACCENT_HOVER};
    background-color: {_ACCENT_DIM};
}}
"""

BACK_BUTTON_STYLE = f"""
QPushButton {{
    background-color: transparent;
    border: none;
    color: {TEXT_SECONDARY};
    font-size: 14px;
    font-weight: 500;
    padding: 8px 16px;
    text-align: left;
}}

QPushButton:hover {{
    color: {ACCENT};
    background-color: transparent;
}}

QPushButton:pressed {{
    color: {ACCENT_HOVER};
}}
"""
