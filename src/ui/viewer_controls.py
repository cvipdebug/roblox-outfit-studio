"""
ui/viewer_controls.py - 3D viewer sidebar controls panel.

Provides:
  - Camera preset buttons
  - Ambient / diffuse lighting sliders
  - Auto-rotate toggle
  - Grid toggle
  - Template type selector (shirt / pants)
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QSlider, QCheckBox, QGroupBox, QComboBox,
    QToolButton, QSizePolicy, QGridLayout,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize


class ViewerControlsPanel(QWidget):
    """
    Control panel for the 3D avatar viewer.

    Signals:
        camera_preset:     Emitted with preset name string.
        ambient_changed:   Emitted with float 0–1.
        diffuse_changed:   Emitted with float 0–1.
        auto_rotate:       Emitted with bool.
        grid_toggled:      Emitted with bool.
        template_changed:  Emitted with "shirt" | "pants".
    """

    camera_preset    = pyqtSignal(str)
    ambient_changed  = pyqtSignal(float)
    diffuse_changed  = pyqtSignal(float)
    auto_rotate      = pyqtSignal(bool)
    grid_toggled     = pyqtSignal(bool)
    template_changed = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        # ── Camera presets ────────────────────────────────────────────────
        cam_group = QGroupBox("Camera")
        cam_layout = QGridLayout(cam_group)
        cam_layout.setSpacing(3)

        presets = [
            ("Front",   "front"),
            ("Back",    "back"),
            ("Left",    "left"),
            ("Right",   "right"),
            ("Top",     "top"),
            ("¾ View",  "threequarter"),
        ]
        for i, (label, key) in enumerate(presets):
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            btn.clicked.connect(lambda _, k=key: self.camera_preset.emit(k))
            cam_layout.addWidget(btn, i // 2, i % 2)

        root.addWidget(cam_group)

        # ── Lighting ──────────────────────────────────────────────────────
        light_group = QGroupBox("Lighting")
        light_layout = QVBoxLayout(light_group)
        light_layout.setSpacing(4)

        amb_row = QHBoxLayout()
        amb_row.addWidget(QLabel("Ambient:"))
        self._ambient_slider = QSlider(Qt.Orientation.Horizontal)
        self._ambient_slider.setRange(0, 100)
        self._ambient_slider.setValue(30)
        self._ambient_slider.valueChanged.connect(
            lambda v: self.ambient_changed.emit(v / 100.0)
        )
        amb_row.addWidget(self._ambient_slider)
        light_layout.addLayout(amb_row)

        diff_row = QHBoxLayout()
        diff_row.addWidget(QLabel("Diffuse:"))
        self._diffuse_slider = QSlider(Qt.Orientation.Horizontal)
        self._diffuse_slider.setRange(0, 100)
        self._diffuse_slider.setValue(80)
        self._diffuse_slider.valueChanged.connect(
            lambda v: self.diffuse_changed.emit(v / 100.0)
        )
        diff_row.addWidget(self._diffuse_slider)
        light_layout.addLayout(diff_row)

        root.addWidget(light_group)

        # ── Options ───────────────────────────────────────────────────────
        opt_group = QGroupBox("Options")
        opt_layout = QVBoxLayout(opt_group)

        self._auto_rotate_check = QCheckBox("Auto Rotate")
        self._auto_rotate_check.toggled.connect(self.auto_rotate.emit)
        opt_layout.addWidget(self._auto_rotate_check)

        self._grid_check = QCheckBox("Show Grid")
        self._grid_check.setChecked(True)
        self._grid_check.toggled.connect(self.grid_toggled.emit)
        opt_layout.addWidget(self._grid_check)

        root.addWidget(opt_group)

        # ── Template selector ─────────────────────────────────────────────
        tmpl_group = QGroupBox("Texture Slot")
        tmpl_layout = QVBoxLayout(tmpl_group)
        self._tmpl_combo = QComboBox()
        self._tmpl_combo.addItems(["shirt", "pants"])
        self._tmpl_combo.currentTextChanged.connect(self.template_changed.emit)
        tmpl_layout.addWidget(self._tmpl_combo)
        root.addWidget(tmpl_group)

        root.addStretch()

        # Instructions
        hint = QLabel(
            "🖱 Left drag: orbit\n"
            "🖱 Right drag: pan\n"
            "🖱 Scroll: zoom"
        )
        hint.setStyleSheet("color: #585b70; font-size: 8pt;;")
        root.addWidget(hint)
