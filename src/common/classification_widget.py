"""Custom Austroads vehicle classification selector widget.

Provides a preset dropdown and a grid of checkboxes for fine-grained
control over which Austroads vehicle classes are active for a job.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from src.common.data_models import (
    AUSTROADS_CLASSES,
    CLASSIFICATION_PRESETS,
    ClassificationConfig,
)
from src.common.theme import (
    ACCENT,
    ACCENT_LIGHT,
    BG_PRIMARY,
    BG_SECONDARY,
    BORDER,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class ClassificationWidget(QGroupBox):
    """Austroads classification selector with presets and custom checkboxes.

    Signals:
        classification_changed(ClassificationConfig): Emitted when the
            user changes the classification selection.
    """

    classification_changed = Signal(object)  # ClassificationConfig

    # Visual grouping of classes
    _GROUPS = [
        ("Active Transport", ["PED", "CYC"]),
        ("Light Vehicles", ["1", "1M", "2"]),
        ("Rigid Heavy Vehicles", ["3", "4", "5"]),
        ("Articulated Vehicles", ["6", "7", "8", "9"]),
        ("Multi-Combination", ["10", "11", "12"]),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Vehicle Classification", parent)
        self._checkboxes: dict[str, QCheckBox] = {}
        self._updating = False  # Prevent signal loops
        self._build_ui()
        self._apply_preset("Lights & Heavies + Active")

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── Preset selector ──
        preset_row = QHBoxLayout()
        preset_label = QLabel("Preset:")
        preset_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-weight: 600; font-size: 12px;")
        self._preset_combo = QComboBox()
        self._preset_combo.addItems(list(CLASSIFICATION_PRESETS.keys()) + ["Custom"])
        self._preset_combo.setCurrentText("Lights & Heavies + Active")
        self._preset_combo.currentTextChanged.connect(self._on_preset_changed)
        preset_row.addWidget(preset_label)
        preset_row.addWidget(self._preset_combo, 1)
        layout.addLayout(preset_row)

        # ── Checkbox grid ──
        self._grid_container = QWidget()
        grid_layout = QVBoxLayout(self._grid_container)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(8)

        for group_name, codes in self._GROUPS:
            group_label = QLabel(group_name)
            group_label.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-weight: 700; font-size: 11px; "
                f"text-transform: uppercase; letter-spacing: 1px; padding-top: 4px;"
            )
            grid_layout.addWidget(group_label)

            row_layout = QHBoxLayout()
            row_layout.setSpacing(16)
            for code in codes:
                info = AUSTROADS_CLASSES.get(code, {})
                label = f"{code} — {info.get('name', code)}"
                cb = QCheckBox(label)
                cb.setToolTip(info.get("description", ""))
                cb.stateChanged.connect(self._on_checkbox_changed)
                self._checkboxes[code] = cb
                row_layout.addWidget(cb)
            row_layout.addStretch()
            grid_layout.addLayout(row_layout)

        layout.addWidget(self._grid_container)

        # ── Summary label ──
        self._summary_label = QLabel()
        self._summary_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 12px; padding-top: 4px;"
        )
        layout.addWidget(self._summary_label)

    def _on_preset_changed(self, preset_name: str) -> None:
        if preset_name != "Custom":
            self._apply_preset(preset_name)

    def _apply_preset(self, preset_name: str) -> None:
        """Check/uncheck boxes to match the named preset."""
        bins = CLASSIFICATION_PRESETS.get(preset_name, [])
        self._updating = True
        for code, cb in self._checkboxes.items():
            cb.setChecked(code in bins)
        self._updating = False
        self._emit_config()

    def _on_checkbox_changed(self) -> None:
        if self._updating:
            return
        # Switch preset combo to "Custom" if checkboxes don't match any preset
        current_bins = self._get_active_bins()
        matched = False
        for name, bins in CLASSIFICATION_PRESETS.items():
            if set(current_bins) == set(bins):
                self._updating = True
                self._preset_combo.setCurrentText(name)
                self._updating = False
                matched = True
                break
        if not matched:
            self._updating = True
            self._preset_combo.setCurrentText("Custom")
            self._updating = False
        self._emit_config()

    def _get_active_bins(self) -> list[str]:
        """Return list of currently checked Austroads codes."""
        return [code for code, cb in self._checkboxes.items() if cb.isChecked()]

    def _emit_config(self) -> None:
        """Build and emit a ClassificationConfig."""
        bins = self._get_active_bins()
        config = ClassificationConfig(
            preset_name=self._preset_combo.currentText(),
            active_bins=bins,
            include_pedestrians="PED" in bins,
            include_cyclists="CYC" in bins,
        )
        # Update summary
        count = len(bins)
        names = config.get_active_class_names()
        if count <= 5:
            self._summary_label.setText(f"{count} classes: {', '.join(names)}")
        else:
            self._summary_label.setText(f"{count} classes selected")
        self.classification_changed.emit(config)

    # ── Public API ──

    def get_config(self) -> ClassificationConfig:
        """Return the current classification configuration."""
        bins = self._get_active_bins()
        return ClassificationConfig(
            preset_name=self._preset_combo.currentText(),
            active_bins=bins,
            include_pedestrians="PED" in bins,
            include_cyclists="CYC" in bins,
        )

    def set_config(self, config: ClassificationConfig) -> None:
        """Programmatically set the classification configuration."""
        self._updating = True
        for code, cb in self._checkboxes.items():
            cb.setChecked(code in config.active_bins)
        self._preset_combo.setCurrentText(config.preset_name)
        self._updating = False
        self._emit_config()
