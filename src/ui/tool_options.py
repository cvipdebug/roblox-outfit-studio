"""
ui/tool_options.py - Tool options sidebar panel.
Designed to fit in a 240px wide dock with no scrolling needed.
"""
from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QSlider, QSpinBox, QDoubleSpinBox, QCheckBox, QComboBox,
    QLineEdit, QPushButton, QColorDialog, QGroupBox, QToolButton,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from core.models import ToolSettings, ToolType, BrushType, Color

# ─── Shared stylesheet fragments ──────────────────────────────────────────────

_GRP = """
QGroupBox {
    font-size: 8pt; font-weight: bold; letter-spacing: 1px;
    color: #7888aa; border: 1px solid #383858; border-radius: 5px;
    margin-top: 8px; padding-top: 2px;
}
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 3px; }
"""

_SPIN = """
QDoubleSpinBox, QSpinBox {
    color: #dde; background: #22223a; border: 1px solid #454565;
    border-radius: 3px; padding: 0 2px; font-size: 8pt;
}
QDoubleSpinBox::up-button, QSpinBox::up-button {
    subcontrol-origin: border; subcontrol-position: top right;
    width: 16px; height: 11px; background: #2c2c48;
    border-left: 1px solid #454565; border-bottom: 1px solid #454565;
    border-top-right-radius: 3px;
}
QDoubleSpinBox::down-button, QSpinBox::down-button {
    subcontrol-origin: border; subcontrol-position: bottom right;
    width: 16px; height: 11px; background: #2c2c48;
    border-left: 1px solid #454565; border-bottom-right-radius: 3px;
}
QDoubleSpinBox::up-arrow, QSpinBox::up-arrow {
    border-left: 3px solid transparent; border-right: 3px solid transparent;
    border-bottom: 4px solid #9090c0; width: 0; height: 0;
}
QDoubleSpinBox::down-arrow, QSpinBox::down-arrow {
    border-left: 3px solid transparent; border-right: 3px solid transparent;
    border-top: 4px solid #9090c0; width: 0; height: 0;
}
QDoubleSpinBox::up-button:hover, QSpinBox::up-button:hover,
QDoubleSpinBox::down-button:hover, QSpinBox::down-button:hover { background: #383860; }
"""

_BTN = """
QPushButton {
    color: #ccd; background: #28283e; border: 1px solid #454565;
    border-radius: 3px; font-size: 8pt; padding: 2px 6px;
}
QPushButton:hover { background: #323250; }
QPushButton:pressed { background: #1c1c30; }
"""

_APPLY = """
QPushButton {
    color: #fff; background: #286028; border: 1px solid #4a904a;
    border-radius: 3px; font-size: 8pt; font-weight: bold; padding: 2px 6px;
}
QPushButton:hover { background: #327832; }
QPushButton:pressed { background: #1c401c; }
"""

_SLIDE = """
QSlider::groove:horizontal { height: 3px; background: #383858; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #5060b8; border-radius: 2px; }
QSlider::handle:horizontal {
    background: #7080d0; border: none;
    width: 12px; height: 12px; margin: -5px 0; border-radius: 6px;
}
"""

_LBL = "color: #aab; font-size: 8pt;"

H = 24   # standard row height

def _grp(title):
    g = QGroupBox(title); g.setStyleSheet(_GRP)
    v = QVBoxLayout(g)
    v.setContentsMargins(8, 14, 8, 8); v.setSpacing(6)
    return g, v

def _lbl(t, w=None):
    l = QLabel(t); l.setStyleSheet(_LBL)
    if w: l.setFixedWidth(w)
    return l

def _spin(lo, hi, val):
    s = QSpinBox(); s.setRange(lo, hi); s.setValue(val)
    s.setStyleSheet(_SPIN); s.setFixedHeight(H); return s

def _dspin(lo, hi, dec, step, sfx=""):
    s = QDoubleSpinBox(); s.setRange(lo, hi); s.setDecimals(dec); s.setSingleStep(step)
    if sfx: s.setSuffix(sfx)
    s.setStyleSheet(_SPIN); s.setFixedHeight(H); return s

def _slide(lo, hi, val):
    s = QSlider(Qt.Orientation.Horizontal)
    s.setRange(lo, hi); s.setValue(val); s.setStyleSheet(_SLIDE)
    s.setFixedHeight(H); return s

def _btn(txt, ss=_BTN):
    b = QPushButton(txt); b.setStyleSheet(ss); b.setFixedHeight(H); return b


# ─── Color swatch ─────────────────────────────────────────────────────────────

class _Swatch(QWidget):
    changed = pyqtSignal(object)

    def __init__(self, color, label, sz=38, parent=None):
        super().__init__(parent)
        self._c = color; self._lbl = label
        self.setFixedSize(sz, sz)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    @property
    def color(self): return self._c
    @color.setter
    def color(self, c): self._c = c; self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        cs = 6
        for r in range(0, self.height(), cs):
            for c in range(0, self.width(), cs):
                p.fillRect(c, r, cs, cs,
                    QColor(170,170,170) if (r+c)//cs%2==0 else QColor(100,100,100))
        p.fillRect(0,0,self.width(),self.height(),
                   QColor(self._c.r, self._c.g, self._c.b, self._c.a))
        p.setPen(QPen(QColor(70,70,100), 1)); p.drawRect(0,0,self.width()-1,self.height()-1)

    def mousePressEvent(self, _):
        qc = QColorDialog.getColor(
            QColor(self._c.r,self._c.g,self._c.b,self._c.a), self,
            f"Choose {self._lbl}", QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if qc.isValid():
            self._c = Color(qc.red(),qc.green(),qc.blue(),qc.alpha())
            self.update(); self.changed.emit(self._c)


# ─── Main panel ───────────────────────────────────────────────────────────────

class ToolOptionsPanel(QWidget):
    tool_settings_changed = pyqtSignal()
    transform_flip_h  = pyqtSignal()
    transform_flip_v  = pyqtSignal()
    transform_reset   = pyqtSignal()
    transform_apply   = pyqtSignal()
    transform_changed = pyqtSignal(float, float, float, float, float)

    def __init__(self, settings: ToolSettings, parent=None):
        super().__init__(parent)
        self._s = settings
        self._upd = False
        self._lock = True
        self._build()
        self.refresh_for_tool(settings.tool)

    # ── Build ─────────────────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6); root.setSpacing(6)

        # ── Colours ──────────────────────────────────────────────────────────
        cg, cl = _grp("COLOURS")

        row1 = QHBoxLayout(); row1.setSpacing(8)
        self._fg = _Swatch(self._s.primary_color,   "foreground")
        self._bg = _Swatch(self._s.secondary_color, "background")
        self._fg.changed.connect(self._on_fg); self._bg.changed.connect(self._on_bg)
        row1.addWidget(_lbl("Fg:")); row1.addWidget(self._fg)
        row1.addWidget(_lbl("Bg:")); row1.addWidget(self._bg)
        row1.addStretch(); cl.addLayout(row1)

        row2 = QHBoxLayout(); row2.setSpacing(6)
        row2.addWidget(_lbl("Hex:"))
        self._hex = QLineEdit(); self._hex.setMaxLength(7)
        self._hex.setPlaceholderText("#RRGGBB"); self._hex.setFixedHeight(H)
        self._hex.setStyleSheet(
            "QLineEdit{color:#dde;background:#22223a;border:1px solid #454565;"
            "border-radius:3px;padding:0 4px;font-size: 8pt;}"
            "QLineEdit:focus{border:1px solid #7080c0;}")
        self._hex.editingFinished.connect(self._on_hex)
        row2.addWidget(self._hex); cl.addLayout(row2)
        root.addWidget(cg)

        # ── Brush ─────────────────────────────────────────────────────────────
        self._bg_brush, bl = _grp("BRUSH")
        self._sz_sl, self._sz_sp = self._slide_row(bl, "Size", 1, 500, self._s.brush_size, self._on_sz)
        self._hd_sl, self._hd_lb = self._pct_row(bl, "Hard", int(self._s.brush_hardness*100), self._on_hd)
        self._op_sl, self._op_lb = self._pct_row(bl, "Opac", int(self._s.brush_opacity*100),  self._on_op)

        # Brush type dropdown
        bt_row = QHBoxLayout(); bt_row.setSpacing(5)
        bt_row.addWidget(_lbl("Type:", 30))
        self._brush_type_combo = QComboBox()
        self._brush_type_combo.setFixedHeight(H)
        self._brush_type_combo.setStyleSheet(
            "QComboBox{color:#dde;background:#22223a;border:1px solid #454565;"
            "border-radius:3px;padding:0 4px;font-size: 8pt;}"
            "QComboBox::drop-down{border-left:1px solid #454565;width:16px;}"
            "QComboBox QAbstractItemView{background:#22223a;color:#dde;selection-background-color:#3a4a80;}")
        self._brush_type_names = [
            ("Hard Round",    BrushType.HARD_ROUND),
            ("Soft Round",    BrushType.SOFT_ROUND),
            ("Airbrush",      BrushType.AIRBRUSH),
            ("Smudge",        BrushType.SMUDGE),
            ("Blend",         BrushType.BLEND),
            ("Chalk",         BrushType.CHALK),
            ("Charcoal",      BrushType.CHARCOAL),
            ("Pencil",        BrushType.PENCIL),
            ("Ink / Lineart", BrushType.INK),
            ("Calligraphy",   BrushType.CALLIGRAPHY),
            ("Flat / Square", BrushType.FLAT),
            ("Texture",       BrushType.TEXTURE),
            ("Scatter",       BrushType.SCATTER),
            ("Watercolor",    BrushType.WATERCOLOR),
            ("Oil Paint",     BrushType.OIL),
            ("Dry Brush",     BrushType.DRY_BRUSH),
            ("Marker",        BrushType.MARKER),
            ("Eraser (soft)", BrushType.ERASER_SOFT),
            ("Eraser (hard)", BrushType.ERASER_HARD),
            ("Pattern",       BrushType.PATTERN),
        ]
        for name, _ in self._brush_type_names:
            self._brush_type_combo.addItem(name)
        # Set default to Soft Round (index 1)
        self._brush_type_combo.setCurrentIndex(1)
        self._brush_type_combo.currentIndexChanged.connect(self._on_brush_type)
        bt_row.addWidget(self._brush_type_combo, 1)
        bl.addLayout(bt_row)
        root.addWidget(self._bg_brush)

        # ── Fill ──────────────────────────────────────────────────────────────
        self._bg_fill, fl = _grp("FILL")
        self._tol_sl, _ = self._slide_row(fl, "Tol", 0, 255, self._s.fill_tolerance, self._on_tol)
        root.addWidget(self._bg_fill)

        # ── Text ──────────────────────────────────────────────────────────────
        self._bg_text, tl = _grp("TEXT")
        fr = QHBoxLayout(); fr.setSpacing(6)
        fr.addWidget(_lbl("Font:", 30))
        self._font = QComboBox()
        self._font.addItems(["Arial","Times New Roman","Courier New","Georgia","Verdana","Impact"])
        self._font.setCurrentText(self._s.font_name); self._font.setFixedHeight(H)
        self._font.setStyleSheet("QComboBox{color:#dde;background:#22223a;border:1px solid #454565;"
            "border-radius:3px;padding:0 4px;font-size: 8pt;}"
            "QComboBox::drop-down{border-left:1px solid #454565;width:16px;}"
            "QComboBox QAbstractItemView{background:#22223a;color:#dde;selection-background-color:#3a4a80;}")
        self._font.currentTextChanged.connect(self._on_font)
        fr.addWidget(self._font, 1); tl.addLayout(fr)

        sr = QHBoxLayout(); sr.setSpacing(6)
        sr.addWidget(_lbl("Size:", 30))
        self._fsize = _spin(6, 200, self._s.font_size)
        self._fsize.valueChanged.connect(self._on_fsize)
        sr.addWidget(self._fsize); sr.addStretch(); tl.addLayout(sr)
        root.addWidget(self._bg_text)

        # ── Shape options ─────────────────────────────────────────────────────
        self._bg_shape, shl = _grp("SHAPE")
        shl_row = QHBoxLayout(); shl_row.setSpacing(5)
        shl_row.addWidget(_lbl("Width:", 38))
        self._shape_lw = _spin(1, 100, self._s.shape_line_width)
        self._shape_lw.setToolTip("Stroke thickness in pixels")
        self._shape_lw.valueChanged.connect(self._on_shape_lw)
        shl_row.addWidget(self._shape_lw); shl_row.addStretch()
        shl.addLayout(shl_row)
        root.addWidget(self._bg_shape)

        # ── Transform ─────────────────────────────────────────────────────────
        self._bg_tx, txl = _grp("TRANSFORM")

        # Grid: label | spinbox | label | spinbox
        g = QGridLayout(); g.setSpacing(5)
        g.setColumnMinimumWidth(0, 26); g.setColumnMinimumWidth(2, 26)
        g.setColumnStretch(1, 1); g.setColumnStretch(3, 1)

        self._tx_x  = _dspin(-4096, 4096, 1, 1)
        self._tx_y  = _dspin(-4096, 4096, 1, 1)
        self._tx_sx = _dspin(0.01, 20, 2, 0.05)
        self._tx_sy = _dspin(0.01, 20, 2, 0.05)
        self._tx_r  = _dspin(-360, 360, 1, 1, "°")

        # Aspect-lock button — sits between W and H spinboxes
        self._lock_btn = QToolButton()
        self._lock_btn.setText("🔗"); self._lock_btn.setCheckable(True); self._lock_btn.setChecked(True)
        self._lock_btn.setFixedSize(20, 20)
        self._lock_btn.setStyleSheet(
            "QToolButton{background:#28283e;border:1px solid #454565;border-radius:3px;font-size: 8pt;}"
            "QToolButton:checked{background:#38386a;border-color:#7080c0;}"
            "QToolButton:hover{background:#323250;}")
        self._lock_btn.toggled.connect(lambda v: setattr(self,'_lock',v) or
                                                  self._lock_btn.setText("🔗" if v else "🔓"))

        g.addWidget(_lbl("X:", 24), 0, 0); g.addWidget(self._tx_x,  0, 1)
        g.addWidget(_lbl("Y:", 24), 0, 2); g.addWidget(self._tx_y,  0, 3)
        g.addWidget(_lbl("W:", 24), 1, 0); g.addWidget(self._tx_sx, 1, 1)
        g.addWidget(self._lock_btn, 1, 2, Qt.AlignmentFlag.AlignCenter)
        g.addWidget(self._tx_sy,    1, 3)
        g.addWidget(_lbl("Rot:", 24), 2, 0); g.addWidget(self._tx_r, 2, 1)
        txl.addLayout(g)

        # Rotate quick buttons — 4 across
        rr = QHBoxLayout(); rr.setSpacing(3)
        for deg, lbl in [(-90,"↺90"),(-45,"↺45"),(45,"↻45"),(90,"↻90")]:
            b = _btn(lbl); b.clicked.connect(lambda _,d=deg: self._rot_by(d))
            rr.addWidget(b)
        txl.addLayout(rr)

        # Flip row
        fr2 = QHBoxLayout(); fr2.setSpacing(5)
        bfh = _btn("⟺ Flip H"); bfv = _btn("⇅ Flip V")
        bfh.clicked.connect(self.transform_flip_h); bfv.clicked.connect(self.transform_flip_v)
        fr2.addWidget(bfh); fr2.addWidget(bfv); txl.addLayout(fr2)

        # Reset / Apply
        ar = QHBoxLayout(); ar.setSpacing(5)
        br = _btn("↺ Reset"); ba = _btn("✓ Apply", _APPLY)
        ba.setToolTip("Bake transform into pixels (undoable)")
        br.clicked.connect(self.transform_reset); ba.clicked.connect(self.transform_apply)
        ar.addWidget(br); ar.addWidget(ba); txl.addLayout(ar)

        for w in (self._tx_x, self._tx_y, self._tx_sx, self._tx_sy, self._tx_r):
            w.valueChanged.connect(self._on_tx)
        root.addWidget(self._bg_tx)

        # ── Grid ──────────────────────────────────────────────────────────────
        gg, gl = _grp("GRID")
        self._snap = QCheckBox("Snap to Grid")
        self._snap.setStyleSheet("QCheckBox{color:#aab;font-size: 8pt;}")
        self._snap.setChecked(self._s.snap_to_grid); self._snap.toggled.connect(self._on_snap)
        gl.addWidget(self._snap)
        gsr = QHBoxLayout(); gsr.setSpacing(6)
        gsr.addWidget(_lbl("Size:", 30))
        self._gspin = _spin(2, 64, self._s.grid_size)
        self._gspin.valueChanged.connect(self._on_gsize)
        gsr.addWidget(self._gspin); gsr.addStretch(); gl.addLayout(gsr)
        root.addWidget(gg)

        root.addStretch()

    # ── Row builders ──────────────────────────────────────────────────────────
    def _slide_row(self, layout, label, lo, hi, val, slot):
        row = QHBoxLayout(); row.setSpacing(5)
        row.addWidget(_lbl(f"{label}:", 30))
        sl = _slide(lo, hi, val); sp = _spin(lo, hi, val)
        sl.valueChanged.connect(lambda v: (sp.blockSignals(True), sp.setValue(v),
                                            sp.blockSignals(False), slot(v)))
        sp.valueChanged.connect(lambda v: (sl.blockSignals(True), sl.setValue(v),
                                            sl.blockSignals(False), slot(v)))
        row.addWidget(sl, 1); row.addWidget(sp)
        layout.addLayout(row); return sl, sp

    def _pct_row(self, layout, label, val, slot):
        row = QHBoxLayout(); row.setSpacing(5)
        row.addWidget(_lbl(f"{label}:", 30))
        sl = _slide(0, 100, val)
        lb = QLabel(f"{val}%"); lb.setStyleSheet(_LBL); lb.setFixedWidth(34)
        lb.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
        sl.valueChanged.connect(lambda v: (lb.setText(f"{v}%"), slot(v)))
        row.addWidget(sl, 1); row.addWidget(lb)
        layout.addLayout(row); return sl, lb

    # ── Public API ────────────────────────────────────────────────────────────
    def refresh_for_tool(self, tool: ToolType):
        self._bg_brush.setVisible(tool in {ToolType.BRUSH, ToolType.ERASER})
        self._bg_fill.setVisible(tool == ToolType.FILL)
        self._bg_text.setVisible(tool == ToolType.TEXT)
        self._bg_shape.setVisible(tool in {ToolType.RECTANGLE, ToolType.ELLIPSE, ToolType.LINE})
        self._bg_tx.setVisible(tool == ToolType.TRANSFORM)

    def set_text_font(self, font_name: str, font_size: int):
        """Update font controls to reflect the selected text object."""
        self._s.font_name = font_name
        self._s.font_size = font_size
        self._font.blockSignals(True)
        self._fsize.blockSignals(True)
        if self._font.findText(font_name) >= 0:
            self._font.setCurrentText(font_name)
        self._fsize.setValue(max(6, min(200, font_size)))
        self._font.blockSignals(False)
        self._fsize.blockSignals(False)

    def set_primary_color(self, color: Color):
        self._s.primary_color = color
        self._fg.color = color; self._hex.setText(color.to_hex())

    def update_transform_display(self, x, y, sx, sy, rot):
        self._upd = True
        self._tx_x.setValue(x);  self._tx_y.setValue(y)
        self._tx_sx.setValue(sx); self._tx_sy.setValue(sy)
        self._tx_r.setValue(rot)
        self._upd = False

    # ── Slots ─────────────────────────────────────────────────────────────────
    def _on_fg(self, c):
        self._s.primary_color = c; self._hex.setText(c.to_hex())
        self.tool_settings_changed.emit()

    def _on_bg(self, c):
        self._s.secondary_color = c; self.tool_settings_changed.emit()

    def _on_hex(self):
        try:
            c = Color.from_hex(self._hex.text().strip(), self._s.primary_color.a)
            self._s.primary_color = c; self._fg.color = c
            self.tool_settings_changed.emit()
        except Exception: pass

    def _on_sz(self, v):  self._s.brush_size = v;           self.tool_settings_changed.emit()
    def _on_hd(self, v):  self._s.brush_hardness = v/100;   self.tool_settings_changed.emit()
    def _on_op(self, v):  self._s.brush_opacity  = v/100;   self.tool_settings_changed.emit()
    def _on_tol(self, v): self._s.fill_tolerance = v;        self.tool_settings_changed.emit()
    def _on_font(self, n):
        if self._upd: return
        self._s.font_name = n
        self.tool_settings_changed.emit()
    def _on_fsize(self, v):
        if self._upd: return
        self._s.font_size = v
        self.tool_settings_changed.emit()
    def _on_snap(self, v): self._s.snap_to_grid = v;         self.tool_settings_changed.emit()

    def _on_brush_type(self, idx):
        _, bt = self._brush_type_names[idx]
        self._s.brush_type = bt
        self.tool_settings_changed.emit()

    def _on_shape_lw(self, v):
        self._s.shape_line_width = v
        self.tool_settings_changed.emit()
    def _on_gsize(self, v): self._s.grid_size = v;           self.tool_settings_changed.emit()

    def _rot_by(self, d):
        if not self._upd:
            self._tx_r.setValue((self._tx_r.value() + d) % 360)

    def _on_tx(self):
        if self._upd: return
        sender = self.sender()
        if self._lock and sender in (self._tx_sx, self._tx_sy):
            self._upd = True
            other = self._tx_sy if sender is self._tx_sx else self._tx_sx
            other.setValue(sender.value())
            self._upd = False
        self.transform_changed.emit(
            self._tx_x.value(), self._tx_y.value(),
            self._tx_sx.value(), self._tx_sy.value(), self._tx_r.value())
