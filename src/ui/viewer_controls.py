"""
ui/viewer_controls.py - 3D viewer sidebar controls panel.
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QSlider, QCheckBox, QGroupBox,
    QToolButton, QColorDialog, QScrollArea, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPixmap, QIcon


class ViewerControlsPanel(QWidget):
    camera_preset      = pyqtSignal(str)
    ambient_changed    = pyqtSignal(float)
    diffuse_changed    = pyqtSignal(float)
    auto_rotate        = pyqtSignal(bool)
    grid_toggled       = pyqtSignal(bool)
    template_changed   = pyqtSignal(str)
    skin_color_changed = pyqtSignal(float, float, float)   # r, g, b 0-1

    _SKIN_DEFAULT = QColor(232, 186, 153)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._skin_color = self._SKIN_DEFAULT
        self._build_ui()

    def _build_ui(self) -> None:
        # Outer layout holds a scroll area so nothing gets clipped
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{border:none;}")

        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(8)

        # ── Camera presets ────────────────────────────────────────────────
        cam_group = QGroupBox("Camera")
        cam_layout = QGridLayout(cam_group)
        cam_layout.setSpacing(3)
        for i, (label, key) in enumerate([
            ("Front", "front"),   ("Back",    "back"),
            ("Left",  "left"),    ("Right",   "right"),
            ("Top",   "top"),     ("¾ View",  "threequarter"),
        ]):
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            btn.clicked.connect(lambda _, k=key: self.camera_preset.emit(k))
            cam_layout.addWidget(btn, i // 2, i % 2)
        root.addWidget(cam_group)

        # ── Lighting ──────────────────────────────────────────────────────
        light_group = QGroupBox("Lighting")
        light_layout = QVBoxLayout(light_group)
        light_layout.setSpacing(4)
        for label, attr, default in [
            ("Ambient:", "_ambient_slider", 30),
            ("Diffuse:",  "_diffuse_slider", 80),
        ]:
            row = QHBoxLayout()
            lbl = QLabel(label); lbl.setFixedWidth(54)
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(0, 100); sl.setValue(default)
            setattr(self, attr, sl)
            row.addWidget(lbl); row.addWidget(sl)
            light_layout.addLayout(row)
        self._ambient_slider.valueChanged.connect(
            lambda v: self.ambient_changed.emit(v / 100.0))
        self._diffuse_slider.valueChanged.connect(
            lambda v: self.diffuse_changed.emit(v / 100.0))
        root.addWidget(light_group)

        # ── Skin color ────────────────────────────────────────────────────
        skin_group = QGroupBox("Skin Color")
        skin_vl = QVBoxLayout(skin_group)
        skin_vl.setSpacing(4)

        # Row 1: color picker button + label
        pick_row = QHBoxLayout()
        self._skin_btn = QPushButton("  Custom…")
        self._skin_btn.setFixedHeight(26)
        self._skin_btn.setToolTip("Click to choose a custom skin color")
        self._skin_btn.clicked.connect(self._on_pick_skin)
        self._update_skin_btn()
        pick_row.addWidget(self._skin_btn)
        pick_row.addStretch()
        skin_vl.addLayout(pick_row)

        # Row 2: preset chips in a wrap grid (3 columns)
        presets = [
            ("#E8BA99", "Classic Yellow"),
            ("#D4956A", "Brown"),
            ("#FFE4C4", "Light"),
            ("#8B4513", "Dark Brown"),
            ("#C8A97A", "Tan"),
            ("#F5DCBB", "Cream"),
            ("#7B3F00", "Deep Brown"),
            ("#FFDAB9", "Peach"),
            ("#A0522D", "Sienna"),
        ]
        chip_grid = QGridLayout()
        chip_grid.setSpacing(3)
        for i, (hex_c, tip) in enumerate(presets):
            chip = QToolButton()
            chip.setFixedSize(24, 24)
            chip.setToolTip(tip)
            pix = QPixmap(20, 20); pix.fill(QColor(hex_c))
            chip.setIcon(QIcon(pix)); chip.setIconSize(chip.size())
            chip.setStyleSheet(
                "QToolButton{border:1px solid #555;border-radius:3px;padding:0;}"
                "QToolButton:hover{border:1px solid #aaf;}")
            chip.clicked.connect(lambda _, h=hex_c: self._set_skin_hex(h))
            chip_grid.addWidget(chip, i // 3, i % 3)
        skin_vl.addLayout(chip_grid)
        root.addWidget(skin_group)

        # ── Texture slot: Shirt / Pants ───────────────────────────────────
        tmpl_group = QGroupBox("Texture Slot")
        tmpl_hl = QHBoxLayout(tmpl_group)
        self._shirt_btn = QPushButton("👕  Shirt")
        self._pants_btn = QPushButton("👖  Pants")
        for btn, val in [(self._shirt_btn, "shirt"), (self._pants_btn, "pants")]:
            btn.setCheckable(True)
            btn.setFixedHeight(30)
            btn.clicked.connect(lambda _, v=val: self._on_template(v))
            tmpl_hl.addWidget(btn)
        self._shirt_btn.setChecked(True)
        self._pants_btn.setChecked(False)
        # Style checked state
        checked_style = (
            "QPushButton{background:#22223a;border:1px solid #454565;"
            "border-radius:4px;color:#cdd6f4;font-size:9pt;}"
            "QPushButton:checked{background:#3a4a80;border:1px solid #89b4fa;color:#fff;}"
            "QPushButton:hover{background:#2a2a4a;}"
        )
        self._shirt_btn.setStyleSheet(checked_style)
        self._pants_btn.setStyleSheet(checked_style)
        root.addWidget(tmpl_group)

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

        root.addStretch()

        hint = QLabel("🖱 Left drag: orbit\n🖱 Right drag: pan\n🖱 Scroll: zoom")
        hint.setStyleSheet("color:#585b70;font-size:8pt;")
        root.addWidget(hint)

        scroll.setWidget(inner)
        outer.addWidget(scroll)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_template(self, val: str):
        self._shirt_btn.setChecked(val == "shirt")
        self._pants_btn.setChecked(val == "pants")
        self.template_changed.emit(val)

    def _on_pick_skin(self):
        col = QColorDialog.getColor(
            self._skin_color, self, "Choose Skin Color")
        if col.isValid():
            self._skin_color = col
            self._update_skin_btn()
            self.skin_color_changed.emit(col.redF(), col.greenF(), col.blueF())

    def _set_skin_hex(self, hex_c: str):
        col = QColor(hex_c)
        self._skin_color = col
        self._update_skin_btn()
        self.skin_color_changed.emit(col.redF(), col.greenF(), col.blueF())

    def _update_skin_btn(self):
        pix = QPixmap(16, 16)
        pix.fill(self._skin_color)
        self._skin_btn.setIcon(QIcon(pix))
        self._skin_btn.setIconSize(pix.size())
