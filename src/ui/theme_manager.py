"""
ui/theme_manager.py - Theme system with shareable JSON config files.
Allows full colour customisation of the app and saves/loads themes.
"""
from __future__ import annotations
import json, os
from typing import Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QGridLayout, QFileDialog, QLineEdit,
    QMessageBox, QColorDialog, QComboBox,
)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt, pyqtSignal

# ── Built-in themes ──────────────────────────────────────────────────────────

BUILTIN_THEMES: dict[str, dict[str, str]] = {
    "Dark (Default)": {
        "window_bg":        "#1e1e2e",
        "panel_bg":         "#181825",
        "widget_bg":        "#313244",
        "border":           "#45475a",
        "text":             "#cdd6f4",
        "text_dim":         "#a6adc8",
        "accent":           "#89b4fa",
        "accent_hover":     "#b4befe",
        "button_bg":        "#313244",
        "button_hover":     "#45475a",
        "selection":        "#89b4fa",
        "canvas_bg":        "#12121c",
        "viewer_bg":        "#1c1c2a",
        "grid_line":        "#313244",
        "toolbar_bg":       "#181825",
        "statusbar_bg":     "#181825",
        "layer_item_bg":    "#313244",
        "layer_item_sel":   "#45475a",
        "layer_item_text":  "#cdd6f4",
        "slider_groove":    "#45475a",
        "slider_handle":    "#89b4fa",
    },
    "Light": {
        "window_bg":        "#eff1f5",
        "panel_bg":         "#e6e9ef",
        "widget_bg":        "#dce0e8",
        "border":           "#bcc0cc",
        "text":             "#4c4f69",
        "text_dim":         "#6c6f85",
        "accent":           "#1e66f5",
        "accent_hover":     "#04a5e5",
        "button_bg":        "#dce0e8",
        "button_hover":     "#bcc0cc",
        "selection":        "#1e66f5",
        "canvas_bg":        "#ccd0da",
        "viewer_bg":        "#dce0e8",
        "grid_line":        "#bcc0cc",
        "toolbar_bg":       "#e6e9ef",
        "statusbar_bg":     "#e6e9ef",
        "layer_item_bg":    "#dce0e8",
        "layer_item_sel":   "#bcc0cc",
        "layer_item_text":  "#4c4f69",
        "slider_groove":    "#bcc0cc",
        "slider_handle":    "#1e66f5",
    },
    "Neon": {
        "window_bg":        "#0d0d0d",
        "panel_bg":         "#0a0a0a",
        "widget_bg":        "#1a1a1a",
        "border":           "#ff007f",
        "text":             "#00ffcc",
        "text_dim":         "#00cc99",
        "accent":           "#ff007f",
        "accent_hover":     "#ff66aa",
        "button_bg":        "#1a1a1a",
        "button_hover":     "#2a2a2a",
        "selection":        "#ff007f",
        "canvas_bg":        "#050505",
        "viewer_bg":        "#080808",
        "grid_line":        "#1a1a1a",
        "toolbar_bg":       "#0a0a0a",
        "statusbar_bg":     "#0a0a0a",
        "layer_item_bg":    "#1a1a1a",
        "layer_item_sel":   "#2a0a1a",
        "layer_item_text":  "#00ffcc",
        "slider_groove":    "#2a2a2a",
        "slider_handle":    "#ff007f",
    },
    "Ocean": {
        "window_bg":        "#0f1923",
        "panel_bg":         "#0a1520",
        "widget_bg":        "#162232",
        "border":           "#1e4060",
        "text":             "#a8d8ea",
        "text_dim":         "#7ab0cc",
        "accent":           "#00b4d8",
        "accent_hover":     "#48cae4",
        "button_bg":        "#162232",
        "button_hover":     "#1e3050",
        "selection":        "#00b4d8",
        "canvas_bg":        "#060e18",
        "viewer_bg":        "#0a1520",
        "grid_line":        "#162232",
        "toolbar_bg":       "#0a1520",
        "statusbar_bg":     "#0a1520",
        "layer_item_bg":    "#162232",
        "layer_item_sel":   "#1e3050",
        "layer_item_text":  "#a8d8ea",
        "slider_groove":    "#1e4060",
        "slider_handle":    "#00b4d8",
    },
}

THEME_KEYS = list(BUILTIN_THEMES["Dark (Default)"].keys())

COLOR_LABELS: dict[str, str] = {
    "window_bg":       "Window Background",
    "panel_bg":        "Panel Background",
    "widget_bg":       "Widget Background",
    "border":          "Borders",
    "text":            "Text",
    "text_dim":        "Dim Text",
    "accent":          "Accent / Highlight",
    "accent_hover":    "Accent Hover",
    "button_bg":       "Button Background",
    "button_hover":    "Button Hover",
    "selection":       "Selection",
    "canvas_bg":       "Canvas Background",
    "viewer_bg":       "3D Viewer Background",
    "grid_line":       "Grid Lines",
    "toolbar_bg":      "Toolbar Background",
    "statusbar_bg":    "Status Bar Background",
    "layer_item_bg":   "Layer Item Background",
    "layer_item_sel":  "Layer Item Selected",
    "layer_item_text": "Layer Item Text",
    "slider_groove":   "Slider Track",
    "slider_handle":   "Slider Handle",
}


def build_stylesheet(t: dict[str, str]) -> str:
    """Generate a Qt stylesheet from a theme dict."""
    return f"""
QMainWindow, QDialog {{
    background: {t['window_bg']};
    color: {t['text']};
}}
QWidget {{
    background: {t['window_bg']};
    color: {t['text']};
    font-size: 9pt;
}}
QDockWidget {{
    background: {t['panel_bg']};
    color: {t['text']};
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}}
QDockWidget::title {{
    background: {t['panel_bg']};
    padding: 4px;
    font-weight: bold;
    color: {t['text_dim']};
    font-size: 8pt;
    letter-spacing: 1px;
}}
QToolBar {{
    background: {t['toolbar_bg']};
    border: none;
    spacing: 2px;
    padding: 2px;
}}
QToolButton {{
    background: {t['button_bg']};
    color: {t['text']};
    border: 1px solid {t['border']};
    border-radius: 4px;
    padding: 3px;
    font-size: 10pt;
}}
QToolButton:hover {{
    background: {t['button_hover']};
    border-color: {t['accent']};
}}
QToolButton:checked {{
    background: {t['accent']};
    color: {t['window_bg']};
    border-color: {t['accent_hover']};
}}
QPushButton {{
    background: {t['button_bg']};
    color: {t['text']};
    border: 1px solid {t['border']};
    border-radius: 4px;
    padding: 4px 10px;
}}
QPushButton:hover {{
    background: {t['button_hover']};
    border-color: {t['accent']};
}}
QPushButton:pressed {{
    background: {t['accent']};
    color: {t['window_bg']};
}}
QMenuBar {{
    background: {t['toolbar_bg']};
    color: {t['text']};
    border-bottom: 1px solid {t['border']};
    font-size: 10pt;
    padding: 1px 4px;
}}
QMenuBar::item {{
    padding: 5px 10px;
    border-radius: 3px;
    background: transparent;
}}
QMenuBar::item:selected {{
    background: {t['accent']};
    color: {t['window_bg']};
}}
QMenu {{
    background: {t['panel_bg']};
    color: {t['text']};
    border: 1px solid {t['border']};
    padding: 4px 0px;
    font-size: 10pt;
}}
QMenu::item {{
    padding: 6px 36px 6px 24px;
    min-width: 210px;
}}
QMenu::item:selected {{
    background: {t['accent']};
    color: {t['window_bg']};
    border-radius: 3px;
}}
QMenu::separator {{
    height: 1px;
    background: {t['border']};
    margin: 4px 8px;
}}
QStatusBar {{
    background: {t['statusbar_bg']};
    color: {t['text_dim']};
    border-top: 1px solid {t['border']};
}}
QListWidget {{
    background: {t['panel_bg']};
    color: {t['text']};
    border: 1px solid {t['border']};
    border-radius: 4px;
    outline: none;
}}
QListWidget::item {{
    background: {t['layer_item_bg']};
    color: {t['layer_item_text']};
    border-bottom: 1px solid {t['border']};
    padding: 2px;
}}
QListWidget::item:selected {{
    background: {t['layer_item_sel']};
    border-left: 3px solid {t['accent']};
}}
QListWidget::item:hover {{
    background: {t['button_hover']};
}}
QSlider::groove:horizontal {{
    background: {t['slider_groove']};
    height: 4px;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {t['slider_handle']};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::sub-page:horizontal {{
    background: {t['accent']};
    border-radius: 2px;
}}
QComboBox {{
    background: {t['widget_bg']};
    color: {t['text']};
    border: 1px solid {t['border']};
    border-radius: 4px;
    padding: 3px 8px;
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background: {t['panel_bg']};
    color: {t['text']};
    border: 1px solid {t['border']};
    selection-background-color: {t['accent']};
}}
QLineEdit, QSpinBox {{
    background: {t['widget_bg']};
    color: {t['text']};
    border: 1px solid {t['border']};
    border-radius: 4px;
    padding: 3px 6px;
}}
QLineEdit:focus, QSpinBox:focus {{
    border-color: {t['accent']};
}}
QLabel {{
    background: transparent;
    color: {t['text']};
}}
QScrollBar:vertical {{
    background: {t['panel_bg']};
    width: 10px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical {{
    background: {t['border']};
    border-radius: 5px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{
    background: {t['accent']};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
}}
QSplitter::handle {{
    background: {t['border']};
    width: 2px;
}}
QGroupBox {{
    border: 1px solid {t['border']};
    border-radius: 6px;
    margin-top: 8px;
    padding-top: 4px;
    color: {t['text_dim']};
    font-size: 8pt;
    font-weight: bold;
    letter-spacing: 1px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}}
QCheckBox {{
    color: {t['text']};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 14px; height: 14px;
    border: 1px solid {t['border']};
    border-radius: 3px;
    background: {t['widget_bg']};
}}
QCheckBox::indicator:checked {{
    background: {t['accent']};
    border-color: {t['accent_hover']};
}}
"""


class ThemeManager:
    """Manages loading, saving and applying themes."""

    CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".outfit_studio_theme.json")

    def __init__(self) -> None:
        self._current: dict[str, str] = dict(BUILTIN_THEMES["Dark (Default)"])
        self._current_name: str = "Dark (Default)"

    def load_config(self) -> None:
        """Load saved theme from config file if it exists."""
        if os.path.exists(self.CONFIG_PATH):
            try:
                with open(self.CONFIG_PATH, "r") as f:
                    data = json.load(f)
                name = data.get("theme_name", "Custom")
                colors = data.get("colors", {})
                self._current_name = name
                base = dict(BUILTIN_THEMES.get(name, BUILTIN_THEMES["Dark (Default)"]))
                base.update(colors)
                self._current = base
            except Exception:
                pass

    def save_config(self) -> None:
        """Save current theme to user config file."""
        data = {"theme_name": self._current_name, "colors": self._current}
        with open(self.CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=2)

    def export_theme(self, path: str) -> None:
        """Export theme to a shareable JSON file."""
        data = {"theme_name": self._current_name, "colors": self._current}
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def import_theme(self, path: str) -> None:
        """Import a theme from a JSON file."""
        with open(path, "r") as f:
            data = json.load(f)
        self._current_name = data.get("theme_name", "Imported")
        self._current = data.get("colors", {})

    def apply_to(self, app) -> None:
        """Apply current theme to a QApplication."""
        app.setStyleSheet(build_stylesheet(self._current))

    @property
    def current(self) -> dict[str, str]:
        return self._current

    @property
    def current_name(self) -> str:
        return self._current_name

    def set_builtin(self, name: str) -> None:
        if name in BUILTIN_THEMES:
            self._current = dict(BUILTIN_THEMES[name])
            self._current_name = name

    def set_color(self, key: str, hex_color: str) -> None:
        self._current[key] = hex_color
        self._current_name = "Custom"

    def get_viewer_bg(self) -> tuple:
        """Return viewer background as (r,g,b) floats 0-1."""
        c = QColor(self._current.get("viewer_bg", "#1c1c2a"))
        return c.redF(), c.greenF(), c.blueF()


# ── Theme Editor Dialog ──────────────────────────────────────────────────────

class ThemeEditorDialog(QDialog):
    """Dialog for editing, importing, and exporting themes."""

    theme_changed = pyqtSignal()

    def __init__(self, manager: ThemeManager, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Theme Editor")
        self.setMinimumSize(480, 560)
        self._manager = manager
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Preset picker
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Preset:"))
        self._preset_combo = QComboBox()
        for name in BUILTIN_THEMES:
            self._preset_combo.addItem(name)
        self._preset_combo.addItem("Custom")
        # Set current
        if self._manager.current_name in BUILTIN_THEMES:
            self._preset_combo.setCurrentText(self._manager.current_name)
        else:
            self._preset_combo.setCurrentText("Custom")
        self._preset_combo.currentTextChanged.connect(self._on_preset_changed)
        preset_row.addWidget(self._preset_combo, 1)
        layout.addLayout(preset_row)

        # Colour swatches grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setSpacing(6)
        self._swatches: dict[str, QPushButton] = {}
        for row, key in enumerate(THEME_KEYS):
            label = QLabel(COLOR_LABELS.get(key, key))
            btn = QPushButton()
            btn.setFixedSize(80, 24)
            self._update_swatch(btn, self._manager.current.get(key, "#ffffff"))
            btn.clicked.connect(lambda _, k=key, b=btn: self._pick_color(k, b))
            grid.addWidget(label, row, 0)
            grid.addWidget(btn, row, 1)
            self._swatches[key] = btn
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)

        # Import / Export / Reset row
        io_row = QHBoxLayout()
        btn_import = QPushButton("Import Theme…")
        btn_export = QPushButton("Export Theme…")
        btn_reset  = QPushButton("Reset to Default")
        btn_import.clicked.connect(self._import)
        btn_export.clicked.connect(self._export)
        btn_reset.clicked.connect(self._reset)
        io_row.addWidget(btn_import)
        io_row.addWidget(btn_export)
        io_row.addWidget(btn_reset)
        layout.addLayout(io_row)

        # OK / Cancel
        btn_row = QHBoxLayout()
        btn_ok = QPushButton("Apply && Close")
        btn_cancel = QPushButton("Cancel")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _update_swatch(self, btn: QPushButton, hex_color: str) -> None:
        c = QColor(hex_color)
        brightness = c.lightnessF()
        text_color = "#000000" if brightness > 0.5 else "#ffffff"
        btn.setText(hex_color)
        btn.setStyleSheet(
            f"background:{hex_color}; color:{text_color}; "
            f"border:1px solid #555; border-radius:3px; font-size: 8pt;"
        )

    def _pick_color(self, key: str, btn: QPushButton) -> None:
        current = QColor(self._manager.current.get(key, "#ffffff"))
        color = QColorDialog.getColor(current, self, f"Choose colour for: {COLOR_LABELS.get(key, key)}")
        if color.isValid():
            hex_c = color.name()
            self._manager.set_color(key, hex_c)
            self._update_swatch(btn, hex_c)
            self._preset_combo.setCurrentText("Custom")
            self.theme_changed.emit()

    def _on_preset_changed(self, name: str) -> None:
        if name in BUILTIN_THEMES:
            self._manager.set_builtin(name)
            for key, btn in self._swatches.items():
                self._update_swatch(btn, self._manager.current.get(key, "#ffffff"))
            self.theme_changed.emit()

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import Theme", "", "Theme files (*.json)")
        if path:
            try:
                self._manager.import_theme(path)
                for key, btn in self._swatches.items():
                    self._update_swatch(btn, self._manager.current.get(key, "#ffffff"))
                self._preset_combo.setCurrentText("Custom")
                self.theme_changed.emit()
            except Exception as e:
                QMessageBox.warning(self, "Import Failed", str(e))

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Theme", "my_theme.json", "Theme files (*.json)")
        if path:
            self._manager.export_theme(path)

    def _reset(self) -> None:
        self._manager.set_builtin("Dark (Default)")
        for key, btn in self._swatches.items():
            self._update_swatch(btn, self._manager.current.get(key, "#ffffff"))
        self._preset_combo.setCurrentText("Dark (Default)")
        self.theme_changed.emit()
