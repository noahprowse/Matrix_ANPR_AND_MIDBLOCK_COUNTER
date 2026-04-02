"""Settings page for Matrix Traffic Data Extraction.

Full-width settings panel with categorized configuration sections:
Storage, API Keys, AI Configuration, Rego Lookup, and About.
All settings persist to ~/.matrix_traffic/settings.json.
"""

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QPushButton,
    QScrollArea,
    QFileDialog,
    QDoubleSpinBox,
    QSpinBox,
    QSizePolicy,
    QSpacerItem,
)
from PySide6.QtCore import Signal, Qt, QTimer
from PySide6.QtGui import QFont

from src.common.theme import (
    BACK_BUTTON_STYLE,
    BG_PRIMARY,
    BG_SECONDARY,
    SURFACE_CARD,
    ACCENT,
    ACCENT_HOVER,
    ACCENT_LIGHT,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_MUTED,
    BORDER,
    INPUT_BG,
    SUCCESS,
    DANGER,
    WARNING,
)

logger = logging.getLogger(__name__)

# Application version
APP_VERSION = "v3.0.0"


# ===========================================================================
# Settings persistence
# ===========================================================================


class AppSettings:
    """Singleton that manages application settings with JSON persistence.

    All settings are stored in ``~/.matrix_traffic/settings.json``.
    Access via ``AppSettings.instance()``.
    """

    _instance: "AppSettings | None" = None

    DEFAULTS: dict[str, Any] = {
        # Storage
        "database_path": "",
        "cloud_enabled": False,
        "cloud_connection": "",
        "cloud_container": "anpr-data",
        # API Keys
        "claude_api_key": "",
        "rego_api_username": "",
        "rego_api_password": "",
        # AI Config
        "anpr_ai_enabled": False,
        "anpr_ai_model": "haiku",
        "counter_ai_enabled": False,
        "counter_ai_model": "haiku",
        "ai_confidence_threshold": 0.65,
        # Rego Lookup
        "rego_enabled": False,
        "rego_default_state": "NSW",
        "rego_auto_lookup": False,
        # Processing
        "max_concurrent_streams": 4,
        "max_gpu_instances": 4,
        "default_preview_enabled": True,
    }

    @classmethod
    def instance(cls) -> "AppSettings":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self._settings: dict[str, Any] = dict(self.DEFAULTS)
        self._path = self._get_settings_path()
        self.load()

    # -- path ---------------------------------------------------------------

    @staticmethod
    def _get_settings_path() -> Path:
        folder = Path.home() / ".matrix_traffic"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / "settings.json"

    # -- storage properties -------------------------------------------------

    @property
    def database_path(self) -> str:
        val = self._settings.get("database_path", "")
        return val if val else os.getcwd()

    @database_path.setter
    def database_path(self, value: str) -> None:
        self._settings["database_path"] = value

    @property
    def cloud_enabled(self) -> bool:
        return bool(self._settings.get("cloud_enabled", False))

    @cloud_enabled.setter
    def cloud_enabled(self, value: bool) -> None:
        self._settings["cloud_enabled"] = value

    @property
    def cloud_connection(self) -> str:
        return self._settings.get("cloud_connection", "")

    @cloud_connection.setter
    def cloud_connection(self, value: str) -> None:
        self._settings["cloud_connection"] = value

    @property
    def cloud_container(self) -> str:
        return self._settings.get("cloud_container", "anpr-data")

    @cloud_container.setter
    def cloud_container(self, value: str) -> None:
        self._settings["cloud_container"] = value

    # -- API key properties -------------------------------------------------

    @property
    def claude_api_key(self) -> str:
        return self._settings.get("claude_api_key", "")

    @claude_api_key.setter
    def claude_api_key(self, value: str) -> None:
        self._settings["claude_api_key"] = value

    @property
    def rego_api_username(self) -> str:
        return self._settings.get("rego_api_username", "")

    @rego_api_username.setter
    def rego_api_username(self, value: str) -> None:
        self._settings["rego_api_username"] = value

    @property
    def rego_api_password(self) -> str:
        return self._settings.get("rego_api_password", "")

    @rego_api_password.setter
    def rego_api_password(self, value: str) -> None:
        self._settings["rego_api_password"] = value

    # -- AI config properties -----------------------------------------------

    @property
    def anpr_ai_enabled(self) -> bool:
        return bool(self._settings.get("anpr_ai_enabled", False))

    @anpr_ai_enabled.setter
    def anpr_ai_enabled(self, value: bool) -> None:
        self._settings["anpr_ai_enabled"] = value

    @property
    def anpr_ai_model(self) -> str:
        return self._settings.get("anpr_ai_model", "haiku")

    @anpr_ai_model.setter
    def anpr_ai_model(self, value: str) -> None:
        self._settings["anpr_ai_model"] = value

    @property
    def counter_ai_enabled(self) -> bool:
        return bool(self._settings.get("counter_ai_enabled", False))

    @counter_ai_enabled.setter
    def counter_ai_enabled(self, value: bool) -> None:
        self._settings["counter_ai_enabled"] = value

    @property
    def counter_ai_model(self) -> str:
        return self._settings.get("counter_ai_model", "haiku")

    @counter_ai_model.setter
    def counter_ai_model(self, value: str) -> None:
        self._settings["counter_ai_model"] = value

    @property
    def ai_confidence_threshold(self) -> float:
        return float(self._settings.get("ai_confidence_threshold", 0.65))

    @ai_confidence_threshold.setter
    def ai_confidence_threshold(self, value: float) -> None:
        self._settings["ai_confidence_threshold"] = value

    # -- rego properties ----------------------------------------------------

    @property
    def rego_enabled(self) -> bool:
        return bool(self._settings.get("rego_enabled", False))

    @rego_enabled.setter
    def rego_enabled(self, value: bool) -> None:
        self._settings["rego_enabled"] = value

    @property
    def rego_default_state(self) -> str:
        return self._settings.get("rego_default_state", "NSW")

    @rego_default_state.setter
    def rego_default_state(self, value: str) -> None:
        self._settings["rego_default_state"] = value

    @property
    def rego_auto_lookup(self) -> bool:
        return bool(self._settings.get("rego_auto_lookup", False))

    @rego_auto_lookup.setter
    def rego_auto_lookup(self, value: bool) -> None:
        self._settings["rego_auto_lookup"] = value

    # -- processing properties ----------------------------------------------

    @property
    def max_concurrent_streams(self) -> int:
        return int(self._settings.get("max_concurrent_streams", 4))

    @max_concurrent_streams.setter
    def max_concurrent_streams(self, value: int) -> None:
        self._settings["max_concurrent_streams"] = max(1, min(24, value))

    @property
    def max_gpu_instances(self) -> int:
        return int(self._settings.get("max_gpu_instances", 4))

    @max_gpu_instances.setter
    def max_gpu_instances(self, value: int) -> None:
        self._settings["max_gpu_instances"] = max(1, min(8, value))

    @property
    def default_preview_enabled(self) -> bool:
        return bool(self._settings.get("default_preview_enabled", True))

    @default_preview_enabled.setter
    def default_preview_enabled(self, value: bool) -> None:
        self._settings["default_preview_enabled"] = value

    # -- persistence --------------------------------------------------------

    def save(self) -> None:
        """Write current settings to disk."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(self._settings, fh, indent=2)
            logger.debug("Settings saved to %s", self._path)
        except Exception:
            logger.exception("Failed to save settings to %s", self._path)

    def load(self) -> None:
        """Load settings from disk, falling back to defaults."""
        if not self._path.exists():
            logger.info("No settings file found; using defaults")
            return
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            # Merge loaded values onto defaults so new keys are always present
            for key, default_val in self.DEFAULTS.items():
                self._settings[key] = data.get(key, default_val)
            logger.debug("Settings loaded from %s", self._path)
        except Exception:
            logger.exception("Failed to load settings from %s", self._path)

    def get(self, key: str, default: Any = None) -> Any:
        return self._settings.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._settings[key] = value


# ===========================================================================
# Settings page widget
# ===========================================================================

# Model options for Claude AI
_MODEL_OPTIONS = [
    ("Haiku (fastest, cheapest)", "haiku"),
    ("Sonnet (balanced)", "sonnet"),
    ("Opus (most capable)", "opus"),
]

# Australian states/territories
_STATES = ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"]


class SettingsPage(QWidget):
    """Full-width settings page with categorized configuration sections.

    Designed as a centered scrollable panel (max 800px) with grouped
    settings that auto-save on every change.
    """

    settings_changed = Signal()
    back_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = AppSettings.instance()
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(300)
        self._save_timer.timeout.connect(self._do_save)
        self.setStyleSheet(f"background-color: {BG_PRIMARY};")
        self._build_ui()
        self._load_from_settings()
        self._connect_signals()

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # -- top bar with back button ---------------------------------------
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(16, 12, 16, 0)

        self.back_btn = QPushButton("<  Back")
        self.back_btn.setStyleSheet(BACK_BUTTON_STYLE)
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.clicked.connect(self.back_clicked.emit)
        top_bar.addWidget(self.back_btn)
        top_bar.addStretch()
        outer.addLayout(top_bar)

        # -- page title -----------------------------------------------------
        title = QLabel("Settings")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = QFont("Segoe UI", 26, QFont.Weight.Bold)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; margin-top: 12px;")
        outer.addWidget(title)

        subtitle = QLabel("Configure processing, storage, API keys, AI features, and lookup options")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 13px; margin-bottom: 8px;")
        outer.addWidget(subtitle)

        # -- scroll area wrapping centered content --------------------------
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Center wrapper (max 800px)
        center_widget = QWidget()
        center_widget.setMaximumWidth(800)
        center_widget.setStyleSheet("background: transparent;")
        self._center_layout = QVBoxLayout(center_widget)
        self._center_layout.setContentsMargins(24, 16, 24, 32)
        self._center_layout.setSpacing(20)

        # Build sections
        self._build_processing_section()
        self._build_storage_section()
        self._build_api_keys_section()
        self._build_ai_config_section()
        self._build_rego_section()
        self._build_tensorrt_section()
        self._build_about_section()

        self._center_layout.addSpacerItem(
            QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        )

        # Horizontally center the center_widget
        content_layout.addStretch()
        h_center = QHBoxLayout()
        h_center.addStretch()
        h_center.addWidget(center_widget)
        h_center.addStretch()
        content_layout.addLayout(h_center)
        content_layout.addStretch()

        scroll.setWidget(scroll_content)
        outer.addWidget(scroll)

    # ── Section 0: Processing ─────────────────────────────────────────────

    def _build_processing_section(self) -> None:
        group = self._make_group("Processing Configuration")
        layout = QVBoxLayout(group)
        layout.setSpacing(12)

        proc_desc = QLabel(
            "Configure how many video streams are processed simultaneously. "
            "Higher concurrency uses more RAM and CPU but finishes jobs faster."
        )
        proc_desc.setWordWrap(True)
        proc_desc.setStyleSheet(self._hint_style())
        layout.addWidget(proc_desc)

        # Concurrent streams
        streams_label = QLabel("Maximum Concurrent Video Streams")
        streams_label.setStyleSheet(self._field_label_style())
        layout.addWidget(streams_label)

        streams_row = QHBoxLayout()
        streams_row.setSpacing(12)
        self.streams_spin = QSpinBox()
        self.streams_spin.setRange(1, 24)
        self.streams_spin.setValue(4)
        self.streams_spin.setFixedWidth(80)
        streams_row.addWidget(self.streams_spin)

        streams_hint = QLabel("1–24 streams (default 4). Each stream processes one video at a time.")
        streams_hint.setWordWrap(True)
        streams_hint.setStyleSheet(self._hint_style())
        streams_row.addWidget(streams_hint)
        layout.addLayout(streams_row)

        # RAM estimate
        self._ram_estimate_label = QLabel("")
        self._ram_estimate_label.setStyleSheet(
            f"color: {ACCENT}; font-size: 12px; font-weight: 500; margin-left: 4px;"
        )
        layout.addWidget(self._ram_estimate_label)
        self._update_ram_estimate(4)

        layout.addWidget(self._make_divider())

        # GPU instances
        gpu_label = QLabel("Maximum GPU Instances")
        gpu_label.setStyleSheet(self._field_label_style())
        layout.addWidget(gpu_label)

        gpu_row = QHBoxLayout()
        gpu_row.setSpacing(12)
        self.gpu_spin = QSpinBox()
        self.gpu_spin.setRange(1, 8)
        self.gpu_spin.setValue(4)
        self.gpu_spin.setFixedWidth(80)
        gpu_row.addWidget(self.gpu_spin)

        gpu_hint = QLabel(
            "1–8 GPU slots (default 4). Remaining streams use CPU. "
            "Reduce if running out of GPU memory."
        )
        gpu_hint.setWordWrap(True)
        gpu_hint.setStyleSheet(self._hint_style())
        gpu_row.addWidget(gpu_hint)
        layout.addLayout(gpu_row)

        layout.addWidget(self._make_divider())

        # Preview toggle
        preview_label = QLabel("Video Preview")
        preview_label.setStyleSheet(self._field_label_style())
        layout.addWidget(preview_label)

        self.preview_cb = QCheckBox("Enable video preview by default during processing")
        layout.addWidget(self.preview_cb)

        preview_hint = QLabel(
            "Disabling preview reduces CPU usage. Preview can still be toggled per-stream during processing."
        )
        preview_hint.setWordWrap(True)
        preview_hint.setStyleSheet(self._hint_style())
        layout.addWidget(preview_hint)

        self._center_layout.addWidget(group)

    # ── Section 1: Storage ─────────────────────────────────────────────────

    def _build_storage_section(self) -> None:
        group = self._make_group("Storage Configuration")
        layout = QVBoxLayout(group)
        layout.setSpacing(12)

        # Database path
        db_label = QLabel("Database & Image Storage Path")
        db_label.setStyleSheet(self._field_label_style())
        layout.addWidget(db_label)

        db_desc = QLabel(
            "This is where plate images, vehicle crops, and the lookup database are stored."
        )
        db_desc.setWordWrap(True)
        db_desc.setStyleSheet(self._hint_style())
        layout.addWidget(db_desc)

        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self.db_path_input = QLineEdit()
        self.db_path_input.setPlaceholderText("Current working directory")
        self.db_path_input.setReadOnly(True)
        path_row.addWidget(self.db_path_input)

        self.db_browse_btn = QPushButton("Browse")
        self.db_browse_btn.setFixedWidth(90)
        self.db_browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.db_browse_btn.clicked.connect(self._on_browse_db_path)
        path_row.addWidget(self.db_browse_btn)
        layout.addLayout(path_row)

        self.db_space_label = QLabel("")
        self.db_space_label.setStyleSheet(self._hint_style())
        layout.addWidget(self.db_space_label)

        # Divider
        layout.addWidget(self._make_divider())

        # Cloud upload
        cloud_label = QLabel("Cloud Upload (Azure Blob Storage)")
        cloud_label.setStyleSheet(self._field_label_style())
        layout.addWidget(cloud_label)

        self.cloud_enable_cb = QCheckBox("Enable cloud upload")
        layout.addWidget(self.cloud_enable_cb)

        conn_label = QLabel("Connection string or SAS URL:")
        conn_label.setStyleSheet(self._hint_style())
        layout.addWidget(conn_label)

        self.cloud_conn_input = QLineEdit()
        self.cloud_conn_input.setPlaceholderText(
            "DefaultEndpointsProtocol=https;AccountName=..."
        )
        self.cloud_conn_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.cloud_conn_input)

        container_label = QLabel("Container name:")
        container_label.setStyleSheet(self._hint_style())
        layout.addWidget(container_label)

        self.cloud_container_input = QLineEdit()
        self.cloud_container_input.setPlaceholderText("anpr-data")
        layout.addWidget(self.cloud_container_input)

        cloud_btn_row = QHBoxLayout()
        cloud_btn_row.setSpacing(8)
        self.cloud_test_btn = QPushButton("Test Connection")
        self.cloud_test_btn.setFixedWidth(140)
        self.cloud_test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cloud_test_btn.clicked.connect(self._on_test_cloud)
        cloud_btn_row.addWidget(self.cloud_test_btn)

        self.cloud_status = QLabel("Not configured")
        self.cloud_status.setStyleSheet(self._status_style_muted())
        cloud_btn_row.addWidget(self.cloud_status)
        cloud_btn_row.addStretch()
        layout.addLayout(cloud_btn_row)

        self._center_layout.addWidget(group)

    # ── Section 2: API Keys ───────────────────────────────────────────────

    def _build_api_keys_section(self) -> None:
        group = self._make_group("API Keys")
        layout = QVBoxLayout(group)
        layout.setSpacing(12)

        # Claude API key
        claude_label = QLabel("Claude API Key (Anthropic)")
        claude_label.setStyleSheet(self._field_label_style())
        layout.addWidget(claude_label)

        claude_desc = QLabel("Used for AI-powered plate reading and vehicle classification.")
        claude_desc.setWordWrap(True)
        claude_desc.setStyleSheet(self._hint_style())
        layout.addWidget(claude_desc)

        claude_row = QHBoxLayout()
        claude_row.setSpacing(8)
        self.claude_key_input = QLineEdit()
        self.claude_key_input.setPlaceholderText("sk-ant-api03-...")
        self.claude_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        claude_row.addWidget(self.claude_key_input)

        self.claude_test_btn = QPushButton("Test")
        self.claude_test_btn.setFixedWidth(70)
        self.claude_test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.claude_test_btn.clicked.connect(self._on_test_claude)
        claude_row.addWidget(self.claude_test_btn)
        layout.addLayout(claude_row)

        self.claude_status = QLabel("Not configured")
        self.claude_status.setStyleSheet(self._status_style_muted())
        layout.addWidget(self.claude_status)

        # Divider
        layout.addWidget(self._make_divider())

        # CarRegistrationAPI
        rego_api_label = QLabel("CarRegistrationAPI Credentials")
        rego_api_label.setStyleSheet(self._field_label_style())
        layout.addWidget(rego_api_label)

        rego_api_desc = QLabel("Used for Australian vehicle registration lookups.")
        rego_api_desc.setWordWrap(True)
        rego_api_desc.setStyleSheet(self._hint_style())
        layout.addWidget(rego_api_desc)

        rego_api_link = QLabel(
            f'Get credentials at <a href="https://www.carregistrationapi.com.au" '
            f'style="color: {ACCENT};">carregistrationapi.com.au</a>'
        )
        rego_api_link.setOpenExternalLinks(True)
        rego_api_link.setStyleSheet(self._hint_style())
        layout.addWidget(rego_api_link)

        user_row = QHBoxLayout()
        user_row.setSpacing(8)
        user_label = QLabel("Username:")
        user_label.setFixedWidth(80)
        user_label.setStyleSheet(self._inline_label_style())
        user_row.addWidget(user_label)
        self.rego_user_input = QLineEdit()
        self.rego_user_input.setPlaceholderText("API username")
        user_row.addWidget(self.rego_user_input)
        layout.addLayout(user_row)

        pass_row = QHBoxLayout()
        pass_row.setSpacing(8)
        pass_label = QLabel("Password:")
        pass_label.setFixedWidth(80)
        pass_label.setStyleSheet(self._inline_label_style())
        pass_row.addWidget(pass_label)
        self.rego_pass_input = QLineEdit()
        self.rego_pass_input.setPlaceholderText("API password")
        self.rego_pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        pass_row.addWidget(self.rego_pass_input)
        layout.addLayout(pass_row)

        rego_btn_row = QHBoxLayout()
        rego_btn_row.setSpacing(8)
        self.rego_api_test_btn = QPushButton("Test")
        self.rego_api_test_btn.setFixedWidth(70)
        self.rego_api_test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rego_api_test_btn.clicked.connect(self._on_test_rego_api)
        rego_btn_row.addWidget(self.rego_api_test_btn)

        self.rego_api_status = QLabel("Not configured")
        self.rego_api_status.setStyleSheet(self._status_style_muted())
        rego_btn_row.addWidget(self.rego_api_status)
        rego_btn_row.addStretch()
        layout.addLayout(rego_btn_row)

        self._center_layout.addWidget(group)

    # ── Section 3: AI Configuration ───────────────────────────────────────

    def _build_ai_config_section(self) -> None:
        group = self._make_group("AI Configuration")
        layout = QVBoxLayout(group)
        layout.setSpacing(12)

        cost_note = QLabel("AI mode uses approximately $0.04 per 1,000 plates (Haiku).")
        cost_note.setWordWrap(True)
        cost_note.setStyleSheet(self._hint_style())
        layout.addWidget(cost_note)

        # ANPR AI
        anpr_label = QLabel("ANPR AI Mode")
        anpr_label.setStyleSheet(self._field_label_style())
        layout.addWidget(anpr_label)

        self.anpr_ai_cb = QCheckBox("Enable AI plate validation")
        layout.addWidget(self.anpr_ai_cb)

        anpr_ai_desc = QLabel(
            "When enabled, Claude validates low-confidence plate readings for improved accuracy."
        )
        anpr_ai_desc.setWordWrap(True)
        anpr_ai_desc.setStyleSheet(self._hint_style())
        layout.addWidget(anpr_ai_desc)

        anpr_model_row = QHBoxLayout()
        anpr_model_row.setSpacing(8)
        anpr_model_label = QLabel("Model:")
        anpr_model_label.setFixedWidth(80)
        anpr_model_label.setStyleSheet(self._inline_label_style())
        anpr_model_row.addWidget(anpr_model_label)
        self.anpr_model_combo = QComboBox()
        for display, _value in _MODEL_OPTIONS:
            self.anpr_model_combo.addItem(display, _value)
        anpr_model_row.addWidget(self.anpr_model_combo)
        layout.addLayout(anpr_model_row)

        # Confidence threshold
        thresh_row = QHBoxLayout()
        thresh_row.setSpacing(8)
        thresh_label = QLabel("Confidence\nthreshold:")
        thresh_label.setFixedWidth(80)
        thresh_label.setStyleSheet(self._inline_label_style())
        thresh_row.addWidget(thresh_label)

        self.confidence_spin = QDoubleSpinBox()
        self.confidence_spin.setRange(0.0, 1.0)
        self.confidence_spin.setSingleStep(0.05)
        self.confidence_spin.setDecimals(2)
        self.confidence_spin.setFixedWidth(100)
        thresh_row.addWidget(self.confidence_spin)

        thresh_hint = QLabel("Plates below this confidence are sent to Claude for validation")
        thresh_hint.setStyleSheet(self._hint_style())
        thresh_hint.setWordWrap(True)
        thresh_row.addWidget(thresh_hint)
        layout.addLayout(thresh_row)

        # Divider
        layout.addWidget(self._make_divider())

        # Counter AI
        counter_label = QLabel("Counter AI Mode")
        counter_label.setStyleSheet(self._field_label_style())
        layout.addWidget(counter_label)

        self.counter_ai_cb = QCheckBox("Enable AI vehicle classification")
        layout.addWidget(self.counter_ai_cb)

        counter_ai_desc = QLabel(
            "When enabled, Claude classifies trucks and buses into Austroads sub-classes."
        )
        counter_ai_desc.setWordWrap(True)
        counter_ai_desc.setStyleSheet(self._hint_style())
        layout.addWidget(counter_ai_desc)

        counter_model_row = QHBoxLayout()
        counter_model_row.setSpacing(8)
        counter_model_label = QLabel("Model:")
        counter_model_label.setFixedWidth(80)
        counter_model_label.setStyleSheet(self._inline_label_style())
        counter_model_row.addWidget(counter_model_label)
        self.counter_model_combo = QComboBox()
        for display, _value in _MODEL_OPTIONS:
            self.counter_model_combo.addItem(display, _value)
        counter_model_row.addWidget(self.counter_model_combo)
        layout.addLayout(counter_model_row)

        self._center_layout.addWidget(group)

    # ── Section 4: Rego Lookup ────────────────────────────────────────────

    def _build_rego_section(self) -> None:
        group = self._make_group("Rego Lookup")
        layout = QVBoxLayout(group)
        layout.setSpacing(12)

        self.rego_enable_cb = QCheckBox("Enable registration lookup")
        layout.addWidget(self.rego_enable_cb)

        rego_desc = QLabel(
            "Checks local database first, then queries CarRegistrationAPI.com.au for "
            "vehicle registration details."
        )
        rego_desc.setWordWrap(True)
        rego_desc.setStyleSheet(self._hint_style())
        layout.addWidget(rego_desc)

        state_row = QHBoxLayout()
        state_row.setSpacing(8)
        state_label = QLabel("Default state:")
        state_label.setFixedWidth(100)
        state_label.setStyleSheet(self._inline_label_style())
        state_row.addWidget(state_label)
        self.state_combo = QComboBox()
        for st in _STATES:
            self.state_combo.addItem(st)
        self.state_combo.setFixedWidth(120)
        state_row.addWidget(self.state_combo)
        state_row.addStretch()
        layout.addLayout(state_row)

        self.rego_auto_cb = QCheckBox("Auto-lookup after processing")
        layout.addWidget(self.rego_auto_cb)

        auto_desc = QLabel(
            "When enabled, automatically looks up all detected plates after ANPR "
            "processing completes."
        )
        auto_desc.setWordWrap(True)
        auto_desc.setStyleSheet(self._hint_style())
        layout.addWidget(auto_desc)

        self._center_layout.addWidget(group)

    # ── Section 5: TensorRT Optimization ─────────────────────────────────

    def _build_tensorrt_section(self) -> None:
        """Build the TensorRT GPU optimization section."""
        group = self._make_group("TensorRT Optimization")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        desc = QLabel(
            "Export YOLO models to TensorRT format for 3-4x faster inference. "
            "Requires an NVIDIA GPU with CUDA and TensorRT installed."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        layout.addWidget(desc)

        # Status label
        self._trt_status_label = QLabel("Checking TensorRT availability...")
        self._trt_status_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
        layout.addWidget(self._trt_status_label)

        # Export button
        self._trt_export_btn = QPushButton("Export yolo11x.pt to TensorRT (FP16)")
        self._trt_export_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCENT};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {ACCENT_HOVER};
            }}
            QPushButton:disabled {{
                background-color: {BORDER};
                color: {TEXT_MUTED};
            }}
        """)
        self._trt_export_btn.clicked.connect(self._on_tensorrt_export)
        layout.addWidget(self._trt_export_btn)

        # Result label
        self._trt_result_label = QLabel("")
        self._trt_result_label.setWordWrap(True)
        self._trt_result_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        layout.addWidget(self._trt_result_label)

        self._center_layout.addWidget(group)

        # Deferred status check
        QTimer.singleShot(500, self._check_tensorrt_status)

    def _check_tensorrt_status(self):
        """Check if TensorRT and CUDA are available."""
        try:
            from src.common.tensorrt_export import is_tensorrt_available, is_cuda_available, get_engine_path
            cuda = is_cuda_available()
            trt = is_tensorrt_available()

            if cuda and trt:
                engine = get_engine_path("yolo11x.pt", half=True)
                import os
                if os.path.isfile(engine):
                    self._trt_status_label.setText(f"TensorRT engine found: {engine}")
                    self._trt_status_label.setStyleSheet(f"color: {SUCCESS}; font-size: 12px;")
                    self._trt_export_btn.setText("Re-export yolo11x.pt to TensorRT (FP16)")
                else:
                    self._trt_status_label.setText("CUDA + TensorRT available. Ready to export.")
                    self._trt_status_label.setStyleSheet(f"color: {SUCCESS}; font-size: 12px;")
            elif cuda and not trt:
                self._trt_status_label.setText("CUDA available but TensorRT not installed. pip install tensorrt")
                self._trt_status_label.setStyleSheet(f"color: {WARNING}; font-size: 12px;")
                self._trt_export_btn.setEnabled(False)
            else:
                self._trt_status_label.setText("No NVIDIA GPU detected. TensorRT requires CUDA.")
                self._trt_status_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px;")
                self._trt_export_btn.setEnabled(False)
        except Exception as e:
            self._trt_status_label.setText(f"Error checking TensorRT: {e}")
            self._trt_status_label.setStyleSheet(f"color: {DANGER}; font-size: 12px;")

    def _on_tensorrt_export(self):
        """Handle TensorRT export button click."""
        self._trt_export_btn.setEnabled(False)
        self._trt_export_btn.setText("Exporting... (this may take several minutes)")
        self._trt_result_label.setText("Export in progress...")
        self._trt_result_label.setStyleSheet(f"color: {ACCENT}; font-size: 11px;")

        # Run in a QTimer to avoid blocking the UI thread during import
        QTimer.singleShot(100, self._do_tensorrt_export)

    def _do_tensorrt_export(self):
        """Perform the actual TensorRT export."""
        try:
            from src.common.tensorrt_export import export_to_tensorrt
            result = export_to_tensorrt("yolo11x.pt", half=True)

            if result:
                self._trt_result_label.setText(f"Export successful: {result}")
                self._trt_result_label.setStyleSheet(f"color: {SUCCESS}; font-size: 11px;")
            else:
                self._trt_result_label.setText("Export failed. Check logs for details.")
                self._trt_result_label.setStyleSheet(f"color: {DANGER}; font-size: 11px;")
        except Exception as e:
            self._trt_result_label.setText(f"Export error: {e}")
            self._trt_result_label.setStyleSheet(f"color: {DANGER}; font-size: 11px;")
        finally:
            self._trt_export_btn.setEnabled(True)
            self._trt_export_btn.setText("Export yolo11x.pt to TensorRT (FP16)")

    # ── Section 6: About ──────────────────────────────────────────────────

    def _build_about_section(self) -> None:
        group = self._make_group("About")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        name_label = QLabel("Matrix Traffic Data Extraction")
        name_font = QFont("Segoe UI", 15, QFont.Weight.Bold)
        name_label.setFont(name_font)
        name_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        layout.addWidget(name_label)

        version_label = QLabel(f"Version {APP_VERSION}")
        version_label.setStyleSheet(f"color: {ACCENT}; font-size: 13px;")
        layout.addWidget(version_label)

        build_label = QLabel("ANPR · Midblock Counter · Intersection Counter")
        build_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        layout.addWidget(build_label)

        settings_path_label = QLabel(
            f"Settings file: {AppSettings.instance()._path}"
        )
        settings_path_label.setWordWrap(True)
        settings_path_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; margin-top: 8px;")
        layout.addWidget(settings_path_label)

        self._center_layout.addWidget(group)

    # ── Load settings into UI ─────────────────────────────────────────────

    def _load_from_settings(self) -> None:
        s = self._settings

        # Processing
        self.streams_spin.setValue(s.max_concurrent_streams)
        self.gpu_spin.setValue(s.max_gpu_instances)
        self.preview_cb.setChecked(s.default_preview_enabled)
        self._update_ram_estimate(s.max_concurrent_streams)

        # Storage
        self.db_path_input.setText(s.database_path)
        self._update_free_space(s.database_path)
        self.cloud_enable_cb.setChecked(s.cloud_enabled)
        self.cloud_conn_input.setText(s.cloud_connection)
        self.cloud_container_input.setText(s.cloud_container)
        self._set_cloud_inputs_enabled(s.cloud_enabled)

        # API Keys
        self.claude_key_input.setText(s.claude_api_key)
        self._update_claude_status()
        self.rego_user_input.setText(s.rego_api_username)
        self.rego_pass_input.setText(s.rego_api_password)
        self._update_rego_api_status()

        # AI Config
        self.anpr_ai_cb.setChecked(s.anpr_ai_enabled)
        self._set_model_combo(self.anpr_model_combo, s.anpr_ai_model)
        self.confidence_spin.setValue(s.ai_confidence_threshold)
        self.counter_ai_cb.setChecked(s.counter_ai_enabled)
        self._set_model_combo(self.counter_model_combo, s.counter_ai_model)
        self._set_anpr_ai_inputs_enabled(s.anpr_ai_enabled)
        self._set_counter_ai_inputs_enabled(s.counter_ai_enabled)

        # Rego
        self.rego_enable_cb.setChecked(s.rego_enabled)
        idx = self.state_combo.findText(s.rego_default_state)
        if idx >= 0:
            self.state_combo.setCurrentIndex(idx)
        self.rego_auto_cb.setChecked(s.rego_auto_lookup)
        self._set_rego_inputs_enabled(s.rego_enabled)

    # ── Connect change signals (auto-save) ────────────────────────────────

    def _connect_signals(self) -> None:
        # Processing
        self.streams_spin.valueChanged.connect(self._on_streams_changed)
        self.gpu_spin.valueChanged.connect(self._schedule_save)
        self.preview_cb.toggled.connect(self._schedule_save)

        # Storage
        self.cloud_enable_cb.toggled.connect(self._on_cloud_toggled)
        self.cloud_conn_input.editingFinished.connect(self._schedule_save)
        self.cloud_container_input.editingFinished.connect(self._schedule_save)

        # API Keys
        self.claude_key_input.editingFinished.connect(self._on_claude_key_changed)
        self.rego_user_input.editingFinished.connect(self._on_rego_creds_changed)
        self.rego_pass_input.editingFinished.connect(self._on_rego_creds_changed)

        # AI Config
        self.anpr_ai_cb.toggled.connect(self._on_anpr_ai_toggled)
        self.anpr_model_combo.currentIndexChanged.connect(self._schedule_save)
        self.confidence_spin.valueChanged.connect(self._schedule_save)
        self.counter_ai_cb.toggled.connect(self._on_counter_ai_toggled)
        self.counter_model_combo.currentIndexChanged.connect(self._schedule_save)

        # Rego
        self.rego_enable_cb.toggled.connect(self._on_rego_toggled)
        self.state_combo.currentIndexChanged.connect(self._schedule_save)
        self.rego_auto_cb.toggled.connect(self._schedule_save)

    # ── Slots ─────────────────────────────────────────────────────────────

    def _on_browse_db_path(self) -> None:
        current = self.db_path_input.text() or os.getcwd()
        folder = QFileDialog.getExistingDirectory(
            self, "Select Storage Folder", current
        )
        if folder:
            self.db_path_input.setText(folder)
            self._settings.database_path = folder
            self._update_free_space(folder)
            self._schedule_save()

    def _on_cloud_toggled(self, checked: bool) -> None:
        self._set_cloud_inputs_enabled(checked)
        self._schedule_save()

    def _on_claude_key_changed(self) -> None:
        self._update_claude_status()
        self._schedule_save()

    def _on_rego_creds_changed(self) -> None:
        self._update_rego_api_status()
        self._schedule_save()

    def _on_anpr_ai_toggled(self, checked: bool) -> None:
        self._set_anpr_ai_inputs_enabled(checked)
        self._schedule_save()

    def _on_counter_ai_toggled(self, checked: bool) -> None:
        self._set_counter_ai_inputs_enabled(checked)
        self._schedule_save()

    def _on_rego_toggled(self, checked: bool) -> None:
        self._set_rego_inputs_enabled(checked)
        self._schedule_save()

    def _on_streams_changed(self, value: int) -> None:
        self._update_ram_estimate(value)
        self._schedule_save()

    def _update_ram_estimate(self, streams: int) -> None:
        """Update estimated RAM usage based on stream count."""
        # ~500MB per stream (YOLO model + frame buffers + tracking state)
        ram_gb = streams * 0.5
        self._ram_estimate_label.setText(
            f"Estimated RAM usage: ~{ram_gb:.1f} GB for {streams} stream{'s' if streams != 1 else ''}"
        )

    def _on_test_cloud(self) -> None:
        """Test Azure Blob Storage connection."""
        conn = self.cloud_conn_input.text().strip()
        if not conn:
            self._set_status(self.cloud_status, "Enter a connection string first", "warning")
            return

        try:
            from src.common.blob_storage import ANPRBlobStorage

            container = self.cloud_container_input.text().strip() or "anpr-data"
            if conn.lower().startswith("http"):
                storage = ANPRBlobStorage(account_url=conn, container_name=container)
            else:
                storage = ANPRBlobStorage(connection_string=conn, container_name=container)

            if storage.is_connected():
                self._set_status(self.cloud_status, "Connected", "success")
            else:
                self._set_status(self.cloud_status, "Connection failed", "error")
        except ImportError:
            self._set_status(
                self.cloud_status,
                "azure-storage-blob not installed",
                "error",
            )
        except Exception as exc:
            self._set_status(self.cloud_status, f"Error: {exc}", "error")

    def _on_test_claude(self) -> None:
        """Test Claude API key with a minimal request."""
        key = self.claude_key_input.text().strip()
        if not key:
            self._set_status(self.claude_status, "Enter an API key first", "warning")
            return

        try:
            import anthropic

            client = anthropic.Anthropic(api_key=key)
            # Minimal request to validate the key
            response = client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}],
            )
            if response and response.content:
                self._set_status(self.claude_status, "API key valid", "success")
            else:
                self._set_status(self.claude_status, "Unexpected response", "warning")
        except ImportError:
            self._set_status(
                self.claude_status,
                "anthropic package not installed",
                "error",
            )
        except Exception as exc:
            msg = str(exc)
            if "authentication" in msg.lower() or "api key" in msg.lower():
                self._set_status(self.claude_status, "Invalid API key", "error")
            else:
                self._set_status(self.claude_status, f"Error: {msg[:60]}", "error")

    def _on_test_rego_api(self) -> None:
        """Test CarRegistrationAPI credentials."""
        username = self.rego_user_input.text().strip()
        password = self.rego_pass_input.text().strip()
        if not username or not password:
            self._set_status(self.rego_api_status, "Enter username and password", "warning")
            return

        try:
            import urllib.request
            import urllib.parse

            # Use a known-format test to check if the credentials work
            url = "https://www.carregistrationapi.com.au/api/reg.asmx/CheckAustralia"
            data = urllib.parse.urlencode({
                "RegistrationNumber": "TEST123",
                "State": "NSW",
                "username": username,
                "key": password,
            }).encode("utf-8")

            req = urllib.request.Request(url, data=data)
            req.add_header("Content-Type", "application/x-www-form-urlencoded")

            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                # If we get a response (even error about plate not found),
                # credentials are valid
                if "error" in body.lower() and "unauthorized" in body.lower():
                    self._set_status(self.rego_api_status, "Invalid credentials", "error")
                else:
                    self._set_status(self.rego_api_status, "Credentials valid", "success")
        except Exception as exc:
            msg = str(exc)
            if "401" in msg or "403" in msg:
                self._set_status(self.rego_api_status, "Invalid credentials", "error")
            elif "timeout" in msg.lower() or "urlopen" in msg.lower():
                self._set_status(self.rego_api_status, "Connection timed out", "error")
            else:
                self._set_status(self.rego_api_status, f"Error: {msg[:60]}", "error")

    # ── Save logic ────────────────────────────────────────────────────────

    def _schedule_save(self) -> None:
        """Debounced save: writes settings after a short delay."""
        self._sync_ui_to_settings()
        self._save_timer.start()

    def _do_save(self) -> None:
        self._sync_ui_to_settings()
        self._settings.save()
        self.settings_changed.emit()
        logger.debug("Settings auto-saved")

    def _sync_ui_to_settings(self) -> None:
        s = self._settings
        # Processing
        s.max_concurrent_streams = self.streams_spin.value()
        s.max_gpu_instances = self.gpu_spin.value()
        s.default_preview_enabled = self.preview_cb.isChecked()
        # Storage
        s.database_path = self.db_path_input.text()
        s.cloud_enabled = self.cloud_enable_cb.isChecked()
        s.cloud_connection = self.cloud_conn_input.text()
        s.cloud_container = self.cloud_container_input.text().strip() or "anpr-data"
        # API Keys
        s.claude_api_key = self.claude_key_input.text()
        s.rego_api_username = self.rego_user_input.text()
        s.rego_api_password = self.rego_pass_input.text()
        # AI Config
        s.anpr_ai_enabled = self.anpr_ai_cb.isChecked()
        s.anpr_ai_model = self.anpr_model_combo.currentData() or "haiku"
        s.ai_confidence_threshold = self.confidence_spin.value()
        s.counter_ai_enabled = self.counter_ai_cb.isChecked()
        s.counter_ai_model = self.counter_model_combo.currentData() or "haiku"
        # Rego
        s.rego_enabled = self.rego_enable_cb.isChecked()
        s.rego_default_state = self.state_combo.currentText()
        s.rego_auto_lookup = self.rego_auto_cb.isChecked()

    # ── Helpers ───────────────────────────────────────────────────────────

    def _make_group(self, title: str) -> QGroupBox:
        group = QGroupBox(title)
        group.setStyleSheet(
            f"""
            QGroupBox {{
                background-color: {BG_SECONDARY};
                border: 1px solid {BORDER};
                border-radius: 12px;
                margin-top: 20px;
                padding: 28px 20px 16px 20px;
                font-weight: 700;
                font-size: 12px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 4px 16px;
                color: {TEXT_SECONDARY};
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 1.5px;
            }}
            """
        )
        return group

    def _make_divider(self) -> QLabel:
        divider = QLabel()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background-color: {BORDER}; margin: 4px 0;")
        return divider

    @staticmethod
    def _field_label_style() -> str:
        return f"color: {TEXT_PRIMARY}; font-size: 14px; font-weight: 600;"

    @staticmethod
    def _hint_style() -> str:
        return f"color: {TEXT_MUTED}; font-size: 12px;"

    @staticmethod
    def _inline_label_style() -> str:
        return f"color: {TEXT_SECONDARY}; font-size: 13px;"

    @staticmethod
    def _status_style_muted() -> str:
        return f"color: {TEXT_MUTED}; font-size: 12px;"

    def _set_status(self, label: QLabel, text: str, level: str = "muted") -> None:
        colors = {
            "success": SUCCESS,
            "error": DANGER,
            "warning": WARNING,
            "muted": TEXT_MUTED,
        }
        color = colors.get(level, TEXT_MUTED)
        prefix = {
            "success": "  ",
            "error": "  ",
            "warning": "  ",
        }
        label.setText(f"{prefix.get(level, '')}{text}")
        label.setStyleSheet(f"color: {color}; font-size: 12px;")

    def _update_free_space(self, path: str) -> None:
        try:
            target = path if path and os.path.isdir(path) else os.getcwd()
            usage = shutil.disk_usage(target)
            free_gb = usage.free / (1024 ** 3)
            total_gb = usage.total / (1024 ** 3)
            self.db_space_label.setText(
                f"Free space: {free_gb:.1f} GB / {total_gb:.1f} GB"
            )
        except Exception:
            self.db_space_label.setText("")

    def _update_claude_status(self) -> None:
        key = self.claude_key_input.text().strip()
        if key:
            masked = key[:10] + "..." + key[-4:] if len(key) > 14 else "****"
            self._set_status(self.claude_status, f"Configured ({masked})", "success")
        else:
            self._set_status(self.claude_status, "Not configured", "muted")

    def _update_rego_api_status(self) -> None:
        username = self.rego_user_input.text().strip()
        password = self.rego_pass_input.text().strip()
        if username and password:
            self._set_status(self.rego_api_status, f"Configured ({username})", "success")
        else:
            self._set_status(self.rego_api_status, "Not configured", "muted")

    def _set_cloud_inputs_enabled(self, enabled: bool) -> None:
        self.cloud_conn_input.setEnabled(enabled)
        self.cloud_container_input.setEnabled(enabled)
        self.cloud_test_btn.setEnabled(enabled)
        if not enabled:
            self._set_status(self.cloud_status, "Disabled", "muted")

    def _set_anpr_ai_inputs_enabled(self, enabled: bool) -> None:
        self.anpr_model_combo.setEnabled(enabled)
        self.confidence_spin.setEnabled(enabled)

    def _set_counter_ai_inputs_enabled(self, enabled: bool) -> None:
        self.counter_model_combo.setEnabled(enabled)

    def _set_rego_inputs_enabled(self, enabled: bool) -> None:
        self.state_combo.setEnabled(enabled)
        self.rego_auto_cb.setEnabled(enabled)

    @staticmethod
    def _set_model_combo(combo: QComboBox, value: str) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return
        combo.setCurrentIndex(0)
