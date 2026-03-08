"""
ui/layer_panel.py - Improved layer panel with thumbnail previews,
rename-on-double-click, and cleaner layout.
"""
from __future__ import annotations
from typing import Optional
import numpy as np
from PIL import Image

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QListWidget, QListWidgetItem, QSlider, QLabel,
    QComboBox, QToolButton, QSizePolicy,
    QAbstractItemView, QFrame, QLineEdit, QScrollArea,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QIcon, QColor, QPixmap, QImage, QPainter, QFont

from core.models import CanvasState, Layer, BlendMode


def _layer_thumbnail(layer: Layer, size: int = 40) -> QPixmap:
    """Generate a small checkerboard-backed thumbnail for a layer."""
    try:
        # Use source_pixels directly for thumbnail (shows the actual imported image)
        if layer.source_pixels is not None:
            raw = Image.fromarray(layer.source_pixels, "RGBA")
        else:
            raw = layer.to_pil()
        img = raw.convert("RGBA").resize((size, size), Image.LANCZOS)
        # Checkerboard background
        bg = Image.new("RGBA", (size, size))
        cs = size // 4
        for ry in range(size):
            for rx in range(size):
                light = ((rx // cs) + (ry // cs)) % 2 == 0
                bg.putpixel((rx, ry), (180, 180, 190, 255) if light else (120, 120, 130, 255))
        composite = Image.alpha_composite(bg, img)
        data = composite.tobytes("raw", "RGBA")
        qi   = QImage(data, size, size, QImage.Format.Format_RGBA8888)
        return QPixmap.fromImage(qi)
    except Exception:
        pix = QPixmap(size, size)
        pix.fill(QColor(80, 80, 90))
        return pix


class LayerPanel(QWidget):
    layer_selected  = pyqtSignal(int)
    layers_changed  = pyqtSignal()
    opacity_changed = pyqtSignal(int, float)

    def __init__(self, canvas: CanvasState, parent=None):
        super().__init__(parent)
        self._canvas   = canvas
        self._updating = False
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("LAYERS")
        title.setStyleSheet("color: #a6adc8; font-size: 10px; font-weight: bold; letter-spacing: 2px;")
        hdr.addWidget(title)
        hdr.addStretch()
        root.addLayout(hdr)

        # Layer list
        self._list = QListWidget()
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setMinimumHeight(180)
        self._list.setIconSize(QSize(40, 40))
        self._list.itemClicked.connect(self._on_item_clicked)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._list.model().rowsMoved.connect(self._on_rows_moved)
        root.addWidget(self._list)

        # Opacity row
        op_row = QHBoxLayout()
        op_lbl = QLabel("Opacity")
        op_lbl.setFixedWidth(46)
        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(0, 100)
        self._opacity_slider.setValue(100)
        self._opacity_slider.valueChanged.connect(self._on_opacity_changed)
        self._opacity_value = QLabel("100%")
        self._opacity_value.setFixedWidth(36)
        self._opacity_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        op_row.addWidget(op_lbl)
        op_row.addWidget(self._opacity_slider)
        op_row.addWidget(self._opacity_value)
        root.addLayout(op_row)

        # Blend mode row
        bm_row = QHBoxLayout()
        bm_lbl = QLabel("Blend")
        bm_lbl.setFixedWidth(46)
        self._blend_combo = QComboBox()
        for bm in BlendMode:
            self._blend_combo.addItem(bm.value.replace("_", " ").title(), bm)
        self._blend_combo.currentIndexChanged.connect(self._on_blend_changed)
        bm_row.addWidget(bm_lbl)
        bm_row.addWidget(self._blend_combo)
        root.addLayout(bm_row)

        # Button strip
        btn_row = QHBoxLayout()
        btn_row.setSpacing(3)
        btns = [
            ("＋", "Add Layer (Ctrl+Shift+N)", self._on_add_layer),
            ("✕",  "Delete Layer",             self._on_delete_layer),
            ("⎘",  "Duplicate Layer",           self._on_duplicate_layer),
            ("↑",  "Move Layer Up",             self._on_move_up),
            ("↓",  "Move Layer Down",           self._on_move_down),
            ("⊕",  "Merge Down",                self._on_merge_down),
        ]
        for sym, tip, slot in btns:
            b = QToolButton()
            b.setText(sym)
            b.setToolTip(tip)
            b.setFixedSize(28, 28)
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        btn_row.addStretch()
        root.addLayout(btn_row)

    # ── Refresh ───────────────────────────────────────────────────────────────

    def refresh(self):
        self._updating = True
        self._list.clear()

        for i, layer in enumerate(reversed(self._canvas.layers)):
            real_idx = len(self._canvas.layers) - 1 - i
            item     = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, real_idx)
            item.setSizeHint(QSize(0, 52))

            thumb = _layer_thumbnail(layer, 40)
            item.setIcon(QIcon(thumb))

            # Build display text
            vis_icon  = "👁 " if layer.visible else "⊘ "
            lock_icon = "🔒 " if layer.locked  else ""
            item.setText(f"{vis_icon}{lock_icon}{layer.name}\n  {int(layer.opacity*100)}% | {layer.blend_mode.value}")

            if not layer.visible:
                item.setForeground(QColor("#666888"))

            if real_idx == self._canvas.active_layer_index:
                self._list.addItem(item)
                self._list.setCurrentItem(item)
            else:
                self._list.addItem(item)

        self._sync_controls()
        self._updating = False

    def _sync_controls(self):
        layer = self._canvas.active_layer
        if layer is None:
            return
        self._updating = True
        val = int(layer.opacity * 100)
        self._opacity_slider.setValue(val)
        self._opacity_value.setText(f"{val}%")
        idx = next(
            (i for i in range(self._blend_combo.count())
             if self._blend_combo.itemData(i) == layer.blend_mode), 0)
        self._blend_combo.setCurrentIndex(idx)
        self._updating = False

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_item_clicked(self, item: QListWidgetItem):
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is not None:
            self._canvas.active_layer_index = idx
            self._sync_controls()
            self.layer_selected.emit(idx)

    def _on_item_double_clicked(self, item: QListWidgetItem):
        """Double-click to toggle visibility, or rename if clicking name area."""
        idx   = item.data(Qt.ItemDataRole.UserRole)
        layer = self._canvas.layers[idx]
        # Toggle visibility on double-click
        layer.visible = not layer.visible
        self.layers_changed.emit()
        self.refresh()

    def _on_rows_moved(self, *args):
        if self._updating:
            return
        new_order = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            idx  = item.data(Qt.ItemDataRole.UserRole)
            if idx is not None:
                new_order.append(self._canvas.layers[idx])
        self._canvas.layers = list(reversed(new_order))
        self._canvas.active_layer_index = max(
            0, min(self._canvas.active_layer_index, len(self._canvas.layers)-1))
        self.layers_changed.emit()
        self.refresh()

    def _on_opacity_changed(self, val: int):
        if self._updating:
            return
        self._opacity_value.setText(f"{val}%")
        layer = self._canvas.active_layer
        if layer:
            layer.opacity = val / 100.0
            self.opacity_changed.emit(self._canvas.active_layer_index, layer.opacity)
            # Update list text
            self.refresh()

    def _on_blend_changed(self, idx: int):
        if self._updating:
            return
        layer = self._canvas.active_layer
        if layer:
            layer.blend_mode = self._blend_combo.itemData(idx)
            self.layers_changed.emit()

    def _on_add_layer(self):
        self._canvas.add_layer()
        self.layers_changed.emit()
        self.refresh()

    def _on_delete_layer(self):
        if len(self._canvas.layers) <= 1:
            return
        self._canvas.remove_layer(self._canvas.active_layer_index)
        self.layers_changed.emit()
        self.refresh()

    def _on_duplicate_layer(self):
        layer = self._canvas.active_layer
        if layer:
            clone = layer.clone()
            clone.name = f"{layer.name} copy"
            self._canvas.layers.insert(self._canvas.active_layer_index+1, clone)
            self._canvas.active_layer_index += 1
            self.layers_changed.emit()
            self.refresh()

    def _on_move_up(self):
        idx = self._canvas.active_layer_index
        if idx < len(self._canvas.layers)-1:
            self._canvas.move_layer(idx, idx+1)
            self._canvas.active_layer_index = idx+1
            self.layers_changed.emit()
            self.refresh()

    def _on_move_down(self):
        idx = self._canvas.active_layer_index
        if idx > 0:
            self._canvas.move_layer(idx, idx-1)
            self._canvas.active_layer_index = idx-1
            self.layers_changed.emit()
            self.refresh()

    def _on_merge_down(self):
        idx = self._canvas.active_layer_index
        if idx == 0:
            return
        top    = self._canvas.layers[idx]
        bottom = self._canvas.layers[idx-1]
        top_img = top.to_pil()
        if top.opacity < 1.0:
            r, g, b, a = top_img.split()
            a = a.point(lambda x: int(x * top.opacity))
            top_img = Image.merge("RGBA", (r, g, b, a))
        merged = Image.alpha_composite(bottom.to_pil(), top_img)
        bottom.pixels = np.array(merged, dtype=np.uint8)
        self._canvas.layers.pop(idx)
        self._canvas.active_layer_index = idx-1
        self.layers_changed.emit()
        self.refresh()

    def _on_visibility_toggled(self, layer_idx: int, visible: bool):
        if 0 <= layer_idx < len(self._canvas.layers):
            self._canvas.layers[layer_idx].visible = visible
            self.layers_changed.emit()

    def _on_lock_toggled(self, layer_idx: int, locked: bool):
        if 0 <= layer_idx < len(self._canvas.layers):
            self._canvas.layers[layer_idx].locked = locked
