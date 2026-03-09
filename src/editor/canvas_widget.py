"""
editor/canvas_widget.py - Interactive 2D painting canvas with
non-destructive Transform tool.

The Transform tool draws live handles (move, scale corners, rotate)
around the active layer's source image. The original pixels are never
modified until you choose Edit → Apply Transform or switch the tool
while holding the state. Switching layers or tools preserves the
transform so you can always come back.
"""
from __future__ import annotations
import math
from typing import Optional, Tuple
import numpy as np
from PIL import Image
from PIL import Image as PILImage

from PyQt6.QtWidgets import QWidget, QSizePolicy, QInputDialog
from PyQt6.QtCore import Qt, QPoint, QPointF, QRectF, QRect, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QImage, QPixmap, QPen, QColor, QBrush,
    QCursor, QMouseEvent, QWheelEvent, QPaintEvent,
    QTransform, QFont,
)
from core.models import CanvasState, ToolSettings, ToolType, Color, BlendMode, LayerTransform, SymmetryAxis
from core.paint_engine import (
    paint_brush_stroke, paint_line, erase_brush_stroke,
    flood_fill, draw_rectangle, draw_ellipse, draw_line_shape,
    draw_text, measure_text, pick_color,
)
from core.history import HistoryManager


# ── Transform handle constants ────────────────────────────────────────────────
HANDLE_R   = 7      # pixel radius of corner / edge handles
ROT_OFFSET = 28     # pixels above top-centre handle for the rotation handle

# Handle IDs
H_NONE       = 0
H_MOVE       = 1
H_TL         = 2   # top-left scale
H_TR         = 3
H_BL         = 4
H_BR         = 5
H_T          = 6   # top-centre scale (uniform Y)
H_B          = 7
H_L          = 8
H_R          = 9
H_ROT        = 10  # rotation knob


class CanvasWidget(QWidget):
    canvas_changed        = pyqtSignal(object)   # PIL Image (flat)
    canvas_replaced       = pyqtSignal(object)   # CanvasState (undo/redo)
    color_picked          = pyqtSignal(object)   # Color
    status_message        = pyqtSignal(str)
    transform_display_update = pyqtSignal(float, float, float, float, float)
    # ^ x, y, scale_x, scale_y, rotation — to sync tool_options spinboxes
    text_object_selected  = pyqtSignal(str, int)   # font_name, font_size
    recent_colors_changed = pyqtSignal()

    def __init__(self, canvas: CanvasState, tools: ToolSettings, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)

        self._canvas  = canvas
        self._tools   = tools
        self._history = HistoryManager(max_steps=100)

        self._zoom:   float = 1.0
        self._pan_x:  float = 0.0
        self._pan_y:  float = 0.0

        # Painting state
        self._drawing:              bool = False
        self._last_canvas_pos:      Optional[Tuple[int,int]] = None
        self._shape_start:          Optional[Tuple[int,int]] = None
        self._shape_preview_pixels: Optional[np.ndarray] = None
        self._panning:              bool = False
        self._pan_start:            Optional[QPoint] = None

        # Brush cursor
        self._mouse_widget_pos: Optional[QPoint] = None

        # Transform tool state
        self._tx_dragging:    int   = H_NONE     # which handle
        self._tx_drag_start:  Optional[QPointF] = None   # widget pos at drag start
        self._tx_saved:       Optional[LayerTransform] = None  # transform at drag start
        self._tx_src_size:    Tuple[int,int] = (0, 0)    # original src image size

        self._composite_cache: Optional[QPixmap] = None
        self._cache_dirty:     bool = True

        # Selection state (None = whole canvas selected)
        self._selection: Optional[Tuple[int,int,int,int]] = None   # x,y,w,h
        self._sel_dragging:   bool = False
        self._sel_start:      Optional[Tuple[int,int]] = None
        self._sel_moving:     bool = False
        self._sel_move_start: Optional[Tuple[int,int]] = None
        self._sel_move_off:   Tuple[int,int] = (0, 0)
        self._sel_float:      Optional[np.ndarray] = None   # cut/floating pixels
        self._sel_float_pos:  Tuple[int,int] = (0, 0)

        # Text objects: list of dicts with keys:
        #   text, x, y, color, font_name, font_size, layer_index
        self._text_objects: list = []
        self._active_text_idx: int = -1   # index into _text_objects, -1=none selected
        self._last_text_idx:   int = -1   # last selected/created — for font size updates
        self._text_dragging:   bool = False
        self._text_drag_off:   tuple = (0, 0)  # offset from text origin to click

        self._rebuild_composite()

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def canvas(self) -> CanvasState:
        return self._canvas

    @canvas.setter
    def canvas(self, value: CanvasState):
        self._canvas = value
        self._tx_dragging = H_NONE
        self._invalidate_cache()

    @property
    def history(self) -> HistoryManager:
        return self._history

    @property
    def zoom(self) -> float:
        return self._zoom

    # ── Cache ─────────────────────────────────────────────────────────────────

    def _invalidate_cache(self):
        self._cache_dirty = True
        self.update()

    def _rebuild_composite(self):
        from PIL import ImageDraw as _PID
        from core.paint_engine import _load_font
        flat = self._canvas.flatten()
        if self._text_objects:
            draw = _PID.Draw(flat, "RGBA")
            for i, obj in enumerate(self._text_objects):
                font = _load_font(obj['font_name'], obj['font_size'])
                c = obj['color']
                draw.text((obj['x'], obj['y']), obj['text'],
                          fill=(c.r, c.g, c.b, c.a), font=font)
                if i == self._active_text_idx:
                    tw, th = measure_text(obj['text'], obj['font_name'], obj['font_size'])
                    tw = max(tw, 20); th = max(th, obj['font_size'])
                    draw.rectangle(
                        [obj['x']-2, obj['y']-2, obj['x']+tw+2, obj['y']+th+2],
                        outline=(80, 160, 255, 200), width=1
                    )
        # Draw floating selection pixels on top
        if self._sel_float is not None:
            from PIL import Image as _flI
            fp = _flI.fromarray(self._sel_float, "RGBA")
            flat.paste(fp, self._sel_float_pos, fp)

        self._composite_cache = _pil_to_pixmap(flat)
        self._cache_dirty = False

    # ── Coordinates ───────────────────────────────────────────────────────────

    def _canvas_origin(self) -> Tuple[float, float]:
        cw = self._canvas.width  * self._zoom
        ch = self._canvas.height * self._zoom
        ox = (self.width()  - cw) / 2 + self._pan_x
        oy = (self.height() - ch) / 2 + self._pan_y
        return ox, oy

    def _widget_to_canvas(self, wx: float, wy: float) -> Tuple[float, float]:
        ox, oy = self._canvas_origin()
        return (wx - ox) / self._zoom, (wy - oy) / self._zoom

    def _canvas_to_widget(self, cx: float, cy: float) -> Tuple[float, float]:
        ox, oy = self._canvas_origin()
        return cx * self._zoom + ox, cy * self._zoom + oy

    def _brush_radius_widget(self) -> float:
        return (self._tools.brush_size / 2.0) * self._zoom

    # ── Transform geometry helpers ────────────────────────────────────────────

    def _tx_layer(self):
        """Return active layer if it has source pixels (transform capable)."""
        layer = self._canvas.active_layer
        if layer and layer.source_pixels is not None:
            return layer
        return None

    def _tx_box_canvas(self) -> Optional[Tuple[float,float,float,float]]:
        """
        Return the transformed bounding box of the active layer in canvas coords:
        (left, top, right, bottom) — axis-aligned, accounting for scale & offset.
        Does NOT account for rotation (rotation is shown via rotated overlay).
        """
        layer = self._tx_layer()
        if layer is None:
            return None
        t = layer.transform
        src_h, src_w = layer.source_pixels.shape[:2]
        sw = src_w * abs(t.scale_x)
        sh = src_h * abs(t.scale_y)
        cx = self._canvas.width  / 2 + t.x
        cy = self._canvas.height / 2 + t.y
        return cx - sw/2, cy - sh/2, cx + sw/2, cy + sh/2

    def _tx_rotated_corners_widget(self) -> Optional[list]:
        """
        Return the 4 corners of the transform box in widget coords,
        rotated by transform.rotation around the box centre.
        Order: TL, TR, BR, BL.
        """
        layer = self._tx_layer()
        if layer is None:
            return None
        t = layer.transform
        src_h, src_w = layer.source_pixels.shape[:2]
        sw = src_w * abs(t.scale_x)
        sh = src_h * abs(t.scale_y)
        cx_c = self._canvas.width  / 2 + t.x
        cy_c = self._canvas.height / 2 + t.y
        angle = math.radians(t.rotation)
        cos_a, sin_a = math.cos(angle), math.sin(angle)

        corners_local = [(-sw/2, -sh/2), (sw/2, -sh/2), (sw/2, sh/2), (-sw/2, sh/2)]
        result = []
        for lx, ly in corners_local:
            rx = lx * cos_a - ly * sin_a + cx_c
            ry = lx * sin_a + ly * cos_a + cy_c
            wx, wy = self._canvas_to_widget(rx, ry)
            result.append(QPointF(wx, wy))
        return result

    def _tx_handles_widget(self) -> dict:
        """Return {handle_id: QPointF} for all transform handles in widget space."""
        corners = self._tx_rotated_corners_widget()
        if corners is None:
            return {}
        tl, tr, br, bl = corners
        tc = QPointF((tl.x()+tr.x())/2, (tl.y()+tr.y())/2)
        bc = QPointF((bl.x()+br.x())/2, (bl.y()+br.y())/2)
        lc = QPointF((tl.x()+bl.x())/2, (tl.y()+bl.y())/2)
        rc = QPointF((tr.x()+br.x())/2, (tr.y()+br.y())/2)
        mc = QPointF((tl.x()+br.x())/2, (tl.y()+br.y())/2)

        # Rotation handle: above top-centre along the top-edge normal
        layer = self._tx_layer()
        t = layer.transform
        angle = math.radians(t.rotation)
        rot_wx = tc.x() - math.sin(angle) * ROT_OFFSET
        rot_wy = tc.y() - math.cos(angle) * ROT_OFFSET

        return {
            H_MOVE: mc,
            H_TL: tl, H_TR: tr, H_BL: bl, H_BR: br,
            H_T: tc,  H_B: bc,  H_L: lc,  H_R: rc,
            H_ROT: QPointF(rot_wx, rot_wy),
        }

    def _tx_hit_handle(self, wx: float, wy: float) -> int:
        """Return handle id under widget position, or H_NONE."""
        handles = self._tx_handles_widget()
        for hid, pt in handles.items():
            if hid == H_MOVE:
                continue
            if math.hypot(wx - pt.x(), wy - pt.y()) <= HANDLE_R + 2:
                return hid
        # Check if inside the box → move
        corners = self._tx_rotated_corners_widget()
        if corners and _point_in_quad(wx, wy, corners):
            return H_MOVE
        return H_NONE

    def _tx_cursor_for_handle(self, hid: int) -> Qt.CursorShape:
        cursors = {
            H_MOVE: Qt.CursorShape.SizeAllCursor,
            H_ROT:  Qt.CursorShape.CrossCursor,
            H_TL:   Qt.CursorShape.SizeFDiagCursor,
            H_BR:   Qt.CursorShape.SizeFDiagCursor,
            H_TR:   Qt.CursorShape.SizeBDiagCursor,
            H_BL:   Qt.CursorShape.SizeBDiagCursor,
            H_T:    Qt.CursorShape.SizeVerCursor,
            H_B:    Qt.CursorShape.SizeVerCursor,
            H_L:    Qt.CursorShape.SizeHorCursor,
            H_R:    Qt.CursorShape.SizeHorCursor,
        }
        return cursors.get(hid, Qt.CursorShape.ArrowCursor)

    # ── Paint event ───────────────────────────────────────────────────────────

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self._zoom < 1.0)

        painter.fillRect(self.rect(), QColor(18, 18, 28))

        if self._cache_dirty:
            self._rebuild_composite()

        ox, oy = self._canvas_origin()
        w = int(self._canvas.width  * self._zoom)
        h = int(self._canvas.height * self._zoom)

        self._draw_checkerboard(painter, int(ox), int(oy), w, h)

        if self._composite_cache:
            painter.drawPixmap(int(ox), int(oy), w, h, self._composite_cache)

        painter.setPen(QPen(QColor(80, 80, 100), 1))
        painter.drawRect(int(ox), int(oy), w, h)

        if self._tools.snap_to_grid and self._zoom >= 4.0:
            self._draw_grid(painter, int(ox), int(oy), w, h)

        # Draw transform overlay on top of everything
        if self._tools.tool == ToolType.TRANSFORM:
            self._draw_transform_overlay(painter)
        else:
            self._draw_brush_cursor(painter)

        # Selection marquee
        if self._selection and self._tools.tool == ToolType.SELECT:
            self._draw_selection_marquee(painter)

        # Symmetry guide lines
        sym = getattr(self._tools, 'symmetry_axis', None)
        if sym and sym.value != 'none':
            self._draw_symmetry_guides(painter)

        painter.end()

    def _draw_checkerboard(self, p, ox, oy, w, h):
        cell  = max(4, int(8 * self._zoom))
        light = QColor(60, 60, 75)
        dark  = QColor(40, 40, 55)
        for row in range(0, h, cell):
            for col in range(0, w, cell):
                color = light if (row//cell + col//cell) % 2 == 0 else dark
                p.fillRect(ox+col, oy+row, min(cell, w-col), min(cell, h-row), color)

    def _draw_grid(self, p, ox, oy, w, h):
        p.setPen(QPen(QColor(80, 80, 100, 100), 1))
        gs = self._tools.grid_size
        for gx in range(0, self._canvas.width, gs):
            px = ox + int(gx * self._zoom)
            p.drawLine(px, oy, px, oy+h)
        for gy in range(0, self._canvas.height, gs):
            py = oy + int(gy * self._zoom)
            p.drawLine(ox, py, ox+w, py)

    def _draw_transform_overlay(self, p: QPainter):
        layer = self._tx_layer()
        if layer is None:
            # Show hint if no source image on this layer
            p.setPen(QColor(120, 120, 160))
            p.setFont(QFont("Arial", 11))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Import an image (File → Import Image as Layer)\nthen select it and use the Transform tool")
            return

        corners = self._tx_rotated_corners_widget()
        handles = self._tx_handles_widget()
        t = layer.transform

        # Dashed bounding box
        pen = QPen(QColor(80, 180, 255), 1.5, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        poly_pts = [corners[0], corners[1], corners[2], corners[3], corners[0]]
        for i in range(4):
            p.drawLine(poly_pts[i], poly_pts[i+1])

        # Line from top-centre to rotation handle
        tc = handles[H_T]
        rh = handles[H_ROT]
        p.setPen(QPen(QColor(80, 180, 255), 1))
        p.drawLine(tc, rh)

        # Draw handles
        for hid, pt in handles.items():
            if hid == H_MOVE:
                continue
            is_corner = hid in (H_TL, H_TR, H_BL, H_BR)
            is_rot    = hid == H_ROT

            if is_rot:
                p.setBrush(QBrush(QColor(255, 200, 50)))
                p.setPen(QPen(QColor(140, 100, 0), 1.5))
                p.drawEllipse(pt, HANDLE_R, HANDLE_R)
                # Arrow symbol
                p.setPen(QPen(QColor(80, 40, 0), 1.5))
                p.setFont(QFont("Arial", 9))
                p.drawText(QRectF(pt.x()-6, pt.y()-6, 12, 12),
                           Qt.AlignmentFlag.AlignCenter, "↻")
            elif is_corner:
                p.setBrush(QBrush(QColor(255, 255, 255)))
                p.setPen(QPen(QColor(80, 140, 255), 1.5))
                p.drawRect(QRectF(pt.x()-HANDLE_R, pt.y()-HANDLE_R, HANDLE_R*2, HANDLE_R*2))
            else:
                p.setBrush(QBrush(QColor(80, 180, 255)))
                p.setPen(QPen(QColor(40, 100, 200), 1.5))
                p.drawRect(QRectF(pt.x()-HANDLE_R+1, pt.y()-HANDLE_R+1, (HANDLE_R-1)*2, (HANDLE_R-1)*2))

        # Status text
        src_h, src_w = layer.source_pixels.shape[:2]
        eff_w = int(src_w * abs(t.scale_x))
        eff_h = int(src_h * abs(t.scale_y))
        info = (f"  {eff_w}×{eff_h}px  "
                f"rot {t.rotation:.1f}°  "
                f"scale {t.scale_x:.2f}×{t.scale_y:.2f}  "
                f"pos ({t.x:+.0f}, {t.y:+.0f})")
        self.status_message.emit(info)

    def _draw_brush_cursor(self, p: QPainter):
        tool = self._tools.tool
        if tool not in (ToolType.BRUSH, ToolType.ERASER):
            return
        if self._mouse_widget_pos is None:
            return
        r = self._brush_radius_widget()
        if r < 1:
            return
        mx = self._mouse_widget_pos.x()
        my = self._mouse_widget_pos.y()
        p.setPen(QPen(QColor(0, 0, 0, 160), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(int(mx-r), int(my-r), int(r*2), int(r*2))
        p.setPen(QPen(QColor(255, 255, 255, 220), 1))
        p.drawEllipse(int(mx-r+1), int(my-r+1), int(r*2-2), int(r*2-2))
        p.setPen(QPen(QColor(255, 255, 255, 200), 1))
        p.drawLine(mx-4, my, mx+4, my)
        p.drawLine(mx, my-4, mx, my+4)

    # ── Zoom & pan ────────────────────────────────────────────────────────────

    def zoom_in(self):
        self._zoom = min(16.0, self._zoom * 1.25); self.update()

    def zoom_out(self):
        self._zoom = max(0.1, self._zoom / 1.25); self.update()

    def zoom_fit(self):
        margin = 40
        zx = (self.width()  - margin) / max(1, self._canvas.width)
        zy = (self.height() - margin) / max(1, self._canvas.height)
        self._zoom  = min(zx, zy)
        self._pan_x = 0.0
        self._pan_y = 0.0
        self.update()

    def zoom_100(self):
        self._zoom = 1.0; self._pan_x = 0.0; self._pan_y = 0.0; self.update()

    # ── Undo / Redo ───────────────────────────────────────────────────────────

    def undo(self):
        state = self._history.undo(self._canvas)
        if state:
            self._canvas = state
            self._tx_dragging = H_NONE
            self._invalidate_cache()
            self.canvas_replaced.emit(self._canvas)
            self.canvas_changed.emit(self._canvas.flatten())

    def redo(self):
        state = self._history.redo(self._canvas)
        if state:
            self._canvas = state
            self._tx_dragging = H_NONE
            self._invalidate_cache()
            self.canvas_replaced.emit(self._canvas)
            self.canvas_changed.emit(self._canvas.flatten())

    def _push_history(self):
        self._history.push(self._canvas)

    def apply_transform(self):
        """Bake the active layer's transform into its pixels permanently."""
        layer = self._tx_layer()
        if layer:
            self._push_history()
            layer.apply_transform()
            self._invalidate_cache()
            self.canvas_changed.emit(self._canvas.flatten())

    def set_transform_from_panel(self, x: float, y: float,
                                  sx: float, sy: float, rot: float):
        """Called when the tool_options spinboxes change — update layer transform live."""
        layer = self._tx_layer()
        if layer is None:
            return
        t = layer.transform
        t.x = x; t.y = y
        t.scale_x = max(0.01, sx)
        t.scale_y = max(0.01, sy)
        t.rotation = rot % 360
        self._invalidate_cache()
        self.canvas_changed.emit(self._canvas.flatten())

    # ── Mouse events ──────────────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        self.setFocus()   # ensure canvas always has keyboard focus after any click
        wx, wy = event.pos().x(), event.pos().y()

        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning   = True
            self._pan_start = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        # ── Transform tool ────────────────────────────────────────────────────
        if self._tools.tool == ToolType.TRANSFORM:
            layer = self._tx_layer()
            if layer is None:
                return
            hid = self._tx_hit_handle(wx, wy)
            if hid != H_NONE:
                self._push_history()
                self._tx_dragging  = hid
                self._tx_drag_start = QPointF(wx, wy)
                self._tx_saved     = layer.transform.copy()
                src_h, src_w = layer.source_pixels.shape[:2]
                self._tx_src_size  = (src_w, src_h)
                self.setCursor(self._tx_cursor_for_handle(hid))
            return

        # ── All other tools ────────────────────────────────────────────────────
        cx_f, cy_f = self._widget_to_canvas(wx, wy)
        cx, cy = int(cx_f), int(cy_f)
        layer  = self._canvas.active_layer
        if layer is None or layer.locked:
            return
        tool = self._tools.tool

        if tool == ToolType.EYEDROPPER:
            color = pick_color(layer.pixels, cx, cy)
            if color:
                self.color_picked.emit(color)
            return

        if tool == ToolType.FILL:
            self._push_history()
            if layer.source_pixels is not None:
                from PIL import Image as _bI
                import numpy as _np2
                raw = _bI.fromarray(layer.source_pixels, "RGBA")
                baked = layer.transform.apply_to_pil(raw, self._canvas.width, self._canvas.height)
                layer.pixels = _np2.array(baked, dtype=_np2.uint8)
                layer.source_pixels = None
                layer.transform = LayerTransform()
            flood_fill(layer.pixels, cx, cy, self._tools.primary_color, self._tools.fill_tolerance)
            self._invalidate_cache()
            self.canvas_changed.emit(self._canvas.flatten())
            return

        if tool == ToolType.SELECT:
            # If floating selection exists, stamp it first
            if self._sel_float is not None:
                self._flatten_float()
                self._canvas_changed_emit()
            self._sel_start    = (cx, cy)
            self._sel_dragging = True
            self._selection    = None
            self._invalidate_cache()
            return

        if tool in (ToolType.RECTANGLE, ToolType.ELLIPSE, ToolType.LINE):
            self._push_history()
            if layer.source_pixels is not None:
                from PIL import Image as _sI
                import numpy as _np3
                raw = _sI.fromarray(layer.source_pixels, "RGBA")
                baked = layer.transform.apply_to_pil(raw, self._canvas.width, self._canvas.height)
                layer.pixels = _np3.array(baked, dtype=_np3.uint8)
                layer.source_pixels = None
                layer.transform = LayerTransform()
            self._shape_start          = (cx, cy)
            self._shape_preview_pixels = layer.pixels.copy()
            self._drawing              = True
            return

        if tool == ToolType.TEXT:
            # Check if clicking an existing text object
            hit = self._text_hit(cx, cy)
            if hit >= 0:
                # Select it for dragging / editing
                self._active_text_idx = hit
                self._last_text_idx   = hit
                tx = self._text_objects[hit]
                self._text_dragging  = True
                self._text_drag_off  = (cx - tx['x'], cy - tx['y'])
                # Push object settings back to tool so panel reflects them
                self._tools.font_name  = tx['font_name']
                self._tools.font_size  = tx['font_size']
                self._tools.primary_color = tx['color']
                self.text_object_selected.emit(tx['font_name'], tx['font_size'])
                self.update()
                return
            # Deselect any existing selection on empty click
            self._active_text_idx = -1
            text, ok = QInputDialog.getText(
                self, "Add Text", "Enter text:",
                text=getattr(self._tools, "text_content", "Text")
            )
            if ok and text.strip():
                self._tools.text_content = text
                obj = {
                    'text':       text,
                    'x':          cx,
                    'y':          cy,
                    'color':      self._tools.primary_color,
                    'font_name':  self._tools.font_name,
                    'font_size':  self._tools.font_size,
                    'layer_index': self._canvas.active_layer_index,
                }
                self._text_objects.append(obj)
                self._active_text_idx = len(self._text_objects) - 1
                self._last_text_idx   = self._active_text_idx
                self._invalidate_cache()
            return

        self._push_history()
        # If this layer has an imported image (source_pixels), bake it into
        # pixels first so the user can paint on top of it directly.
        if layer.source_pixels is not None:
            from PIL import Image as _bakeI
            raw  = _bakeI.fromarray(layer.source_pixels, "RGBA")
            baked = layer.transform.apply_to_pil(raw, self._canvas.width, self._canvas.height)
            import numpy as _np
            layer.pixels      = _np.array(baked, dtype=_np.uint8)
            layer.source_pixels = None
            layer.transform   = LayerTransform()
        self._drawing         = True
        self._last_canvas_pos = (cx, cy)
        self._apply_brush(cx, cy)

    def mouseMoveEvent(self, event: QMouseEvent):
        wx, wy = event.pos().x(), event.pos().y()
        self._mouse_widget_pos = event.pos()

        # ── Panning ────────────────────────────────────────────────────────────
        if self._panning and self._pan_start:
            dx = wx - self._pan_start.x()
            dy = wy - self._pan_start.y()
            self._pan_x += dx; self._pan_y += dy
            self._pan_start = event.pos()
            self.update()
            return

        # ── Transform drag ─────────────────────────────────────────────────────
        if self._tools.tool == ToolType.TRANSFORM:
            layer = self._tx_layer()
            if layer is None:
                self.update()
                return

            if self._tx_dragging != H_NONE and self._tx_drag_start and self._tx_saved:
                self._handle_transform_drag(wx, wy, layer)
                self._invalidate_cache()
                return

            # Hover: update cursor
            hid = self._tx_hit_handle(wx, wy)
            self.setCursor(self._tx_cursor_for_handle(hid) if hid != H_NONE
                           else Qt.CursorShape.ArrowCursor)
            self.update()
            return

        # ── Status bar ─────────────────────────────────────────────────────────
        cx_f, cy_f = self._widget_to_canvas(wx, wy)
        cx, cy = int(cx_f), int(cy_f)
        if 0 <= cx < self._canvas.width and 0 <= cy < self._canvas.height:
            layer = self._canvas.active_layer
            color_str = ""
            if layer and layer.pixels is not None:
                try:
                    px = layer.pixels[cy, cx]
                    color_str = f"  RGBA({px[0]},{px[1]},{px[2]},{px[3]})"
                except IndexError:
                    pass
            self.status_message.emit(f"X:{cx}  Y:{cy}{color_str}  Zoom:{self._zoom*100:.0f}%")

        # Text drag (must be before drawing check)
        tool = self._tools.tool

        # Selection drag
        if tool == ToolType.SELECT and self._sel_dragging and self._sel_start:
            sx, sy = self._sel_start
            x0, y0 = min(sx, cx), min(sy, cy)
            x1, y1 = max(sx, cx), max(sy, cy)
            w = max(1, x1 - x0); h = max(1, y1 - y0)
            self._selection = (x0, y0, w, h)
            self._invalidate_cache()
            return

        # Float drag — move cut/copied pixels
        if tool == ToolType.SELECT and self._sel_float is not None and self._sel_moving:
            if self._sel_move_start:
                ox, oy = self._sel_move_off
                self._sel_float_pos = (cx - ox, cy - oy)
                self._invalidate_cache()
            return

        if tool == ToolType.TEXT and self._text_dragging and self._active_text_idx >= 0:
            obj = self._text_objects[self._active_text_idx]
            obj['x'] = cx - self._text_drag_off[0]
            obj['y'] = cy - self._text_drag_off[1]
            self._invalidate_cache()
            return

        self.update()

        if not self._drawing:
            return

        layer = self._canvas.active_layer
        if layer is None or layer.locked:
            return
        tool = self._tools.tool

        if tool in (ToolType.RECTANGLE, ToolType.ELLIPSE, ToolType.LINE) and self._shape_start:
            preview = self._shape_preview_pixels.copy()
            sx, sy  = self._shape_start
            c       = self._tools.primary_color
            _lw = getattr(self._tools, 'shape_line_width', 2)
            if tool == ToolType.RECTANGLE:
                draw_rectangle(preview, sx, sy, cx, cy, c, False, _lw)
            elif tool == ToolType.ELLIPSE:
                draw_ellipse(preview, sx, sy, cx, cy, c, False, _lw)
            elif tool == ToolType.LINE:
                draw_line_shape(preview, sx, sy, cx, cy, c, _lw)
            self._composite_cache = _pil_to_pixmap(self._make_preview_flat(preview, layer))
            self._cache_dirty = False
            self.update()
            return

        if tool in (ToolType.BRUSH, ToolType.ERASER) and self._last_canvas_pos:
            if tool == ToolType.BRUSH:
                _bt = getattr(self._tools, 'brush_type', None)
                paint_line(layer.pixels, self._last_canvas_pos, (cx, cy),
                           self._tools.primary_color, self._tools.brush_size,
                           self._tools.brush_hardness, self._tools.brush_opacity,
                           brush_type=_bt, stroke_seed=cx ^ cy)
            else:
                x0, y0 = self._last_canvas_pos
                dist   = math.hypot(cx-x0, cy-y0)
                steps  = max(1, int(dist))
                for i in range(steps+1):
                    t = i / steps
                    erase_brush_stroke(layer.pixels, int(x0+t*(cx-x0)), int(y0+t*(cy-y0)),
                                       self._tools.brush_size, self._tools.brush_hardness,
                                       self._tools.brush_opacity)
            self._last_canvas_pos = (cx, cy)
            self._invalidate_cache()

    def _handle_transform_drag(self, wx: float, wy: float, layer):
        """Apply mouse delta to the active transform handle."""
        t   = layer.transform
        sv  = self._tx_saved
        ds  = self._tx_drag_start
        dx  = wx - ds.x()
        dy  = wy - ds.y()
        # Convert delta to canvas units
        dx_c = dx / self._zoom
        dy_c = dy / self._zoom
        src_w, src_h = self._tx_src_size
        hid = self._tx_dragging

        if hid == H_MOVE:
            t.x = sv.x + dx_c
            t.y = sv.y + dy_c

        elif hid == H_ROT:
            # Angle from box centre to current mouse position
            cx_w, cy_w = self._canvas_to_widget(
                self._canvas.width/2 + sv.x,
                self._canvas.height/2 + sv.y)
            angle_start = math.degrees(math.atan2(ds.y() - cy_w, ds.x() - cx_w))
            angle_now   = math.degrees(math.atan2(wy - cy_w, wx - cx_w))
            t.rotation  = (sv.rotation + angle_now - angle_start) % 360

        elif hid in (H_TL, H_TR, H_BL, H_BR, H_T, H_B, H_L, H_R):
            # Delta-based scaling: pixels dragged / (half the current image size in widget px)
            # This gives 2× scale when you drag one edge all the way to the other side.
            src_w_px = src_w * sv.scale_x * self._zoom   # current half-width in widget pixels
            src_h_px = src_h * sv.scale_y * self._zoom

            half_w = max(1.0, src_w_px / 2.0)
            half_h = max(1.0, src_h_px / 2.0)

            # dx/dy are already in widget pixels (from top of method)
            # Each handle only controls its relevant axis
            if hid in (H_L, H_BL, H_TL):
                # Left edge: dragging right (positive dx) shrinks width
                t.scale_x = max(0.01, sv.scale_x * (1.0 - dx / half_w))
            elif hid in (H_R, H_BR, H_TR):
                # Right edge: dragging right (positive dx) grows width
                t.scale_x = max(0.01, sv.scale_x * (1.0 + dx / half_w))

            if hid in (H_T, H_TL, H_TR):
                # Top edge: dragging down (positive dy) shrinks height
                t.scale_y = max(0.01, sv.scale_y * (1.0 - dy / half_h))
            elif hid in (H_B, H_BL, H_BR):
                # Bottom edge: dragging down (positive dy) grows height
                t.scale_y = max(0.01, sv.scale_y * (1.0 + dy / half_h))

        # Notify tool_options panel so its spinboxes stay in sync
        self.transform_display_update.emit(
            t.x, t.y, t.scale_x, t.scale_y, t.rotation)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        # Stop selection drag
        if self._sel_dragging:
            self._sel_dragging = False
        if self._sel_moving:
            self._sel_moving = False

        # Stop text drag
        if self._text_dragging:
            self._text_dragging = False

        if self._tx_dragging != H_NONE:
            self._tx_dragging   = H_NONE
            self._tx_drag_start = None
            self._tx_saved      = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            layer = self._tx_layer()
            if layer:
                t = layer.transform
                self.transform_display_update.emit(
                    t.x, t.y, t.scale_x, t.scale_y, t.rotation)
            self.canvas_changed.emit(self._canvas.flatten())
            return

        layer = self._canvas.active_layer
        tool  = self._tools.tool

        if self._drawing and self._shape_start and layer and tool in (
            ToolType.RECTANGLE, ToolType.ELLIPSE, ToolType.LINE
        ):
            wx, wy = event.pos().x(), event.pos().y()
            cx, cy = int(*self._widget_to_canvas(wx, wy)) if False else (
                int(self._widget_to_canvas(wx, wy)[0]),
                int(self._widget_to_canvas(wx, wy)[1]),
            )
            sx, sy = self._shape_start
            c = self._tools.primary_color
            lw = getattr(self._tools, "shape_line_width", 2)
            if tool == ToolType.RECTANGLE:
                draw_rectangle(layer.pixels, sx, sy, cx, cy, c, False, lw)
            elif tool == ToolType.ELLIPSE:
                draw_ellipse(layer.pixels, sx, sy, cx, cy, c, False, lw)
            elif tool == ToolType.LINE:
                draw_line_shape(layer.pixels, sx, sy, cx, cy, c, lw)
            self._shape_start = None; self._shape_preview_pixels = None
            self._invalidate_cache()
            self.canvas_changed.emit(self._canvas.flatten())

        if self._drawing and layer:
            self.canvas_changed.emit(self._canvas.flatten())

        self._drawing = False; self._last_canvas_pos = None

    def _draw_selection_marquee(self, p):
        from PyQt6.QtCore import Qt as _Qt
        if not self._selection:
            return
        ox, oy = self._canvas_origin()
        x, y, w, h = self._selection
        rx = int(ox + x * self._zoom)
        ry = int(oy + y * self._zoom)
        rw = int(w * self._zoom)
        rh = int(h * self._zoom)
        # Animated dashes via tick — just use a fixed dash for simplicity
        pen = QPen(QColor(255, 255, 255, 220), 1, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawRect(rx, ry, rw, rh)
        pen2 = QPen(QColor(0, 0, 0, 180), 1, Qt.PenStyle.DashLine)
        pen2.setDashOffset(4)
        p.setPen(pen2)
        p.drawRect(rx, ry, rw, rh)

    def _draw_symmetry_guides(self, p):
        from core.models import SymmetryAxis as _SA
        sym = getattr(self._tools, 'symmetry_axis', None)
        if not sym or sym == _SA.NONE:
            return
        ox, oy = self._canvas_origin()
        W = self._canvas.width  * self._zoom
        H = self._canvas.height * self._zoom
        pen = QPen(QColor(80, 200, 255, 120), 1, Qt.PenStyle.DashLine)
        p.setPen(pen)
        if sym in (_SA.HORIZONTAL, _SA.BOTH):
            mx = int(ox + W / 2)
            p.drawLine(mx, int(oy), mx, int(oy + H))
        if sym in (_SA.VERTICAL, _SA.BOTH):
            my = int(oy + H / 2)
            p.drawLine(int(ox), my, int(ox + W), my)

    def mouseDoubleClickEvent(self, event):
        """Double-click a text object to edit it."""
        if self._tools.tool != ToolType.TEXT:
            return
        wx, wy = event.pos().x(), event.pos().y()
        cx_f, cy_f = self._widget_to_canvas(wx, wy)
        cx, cy = int(cx_f), int(cy_f)
        hit = self._text_hit(cx, cy)
        if hit >= 0:
            obj = self._text_objects[hit]
            text, ok = QInputDialog.getText(
                self, "Edit Text", "Edit text:", text=obj['text']
            )
            if ok and text.strip():
                obj['text'] = text
                self._invalidate_cache()
            elif ok and not text.strip():
                # Empty text = delete
                self._bake_text(hit)
                del self._text_objects[hit]
                self._active_text_idx = -1
                self._invalidate_cache()

    def keyPressEvent(self, event):
        """Handle all keyboard shortcuts directly on the canvas widget."""
        from PyQt6.QtCore import Qt as _Qt
        key  = event.key()
        ctrl = event.modifiers() & _Qt.KeyboardModifier.ControlModifier
        shift= event.modifiers() & _Qt.KeyboardModifier.ShiftModifier

        # ── Text tool keys ────────────────────────────────────────────────────
        if self._tools.tool == ToolType.TEXT and self._active_text_idx >= 0:
            if key == _Qt.Key.Key_Delete:
                self._bake_text(self._active_text_idx)
                del self._text_objects[self._active_text_idx]
                self._active_text_idx = -1
                self._invalidate_cache()
                return
            if key in (_Qt.Key.Key_Return, _Qt.Key.Key_Enter):
                self._bake_text(self._active_text_idx)
                del self._text_objects[self._active_text_idx]
                self._active_text_idx = -1
                self._invalidate_cache()
                return

        # ── Selection shortcuts (always active) ───────────────────────────────
        if ctrl and key == _Qt.Key.Key_A:
            self.select_all(); return
        if ctrl and key == _Qt.Key.Key_D:
            self.clear_selection(); return
        if ctrl and key == _Qt.Key.Key_C:
            self.copy_selection(); return
        if ctrl and key == _Qt.Key.Key_X:
            self.cut_selection(); return
        if ctrl and key == _Qt.Key.Key_V:
            self.paste_selection(); return
        if key == _Qt.Key.Key_Escape:
            if self._sel_float is not None:
                self.paste_selection()   # drop float on Escape
            else:
                self.clear_selection()
            return
        if key == _Qt.Key.Key_Delete and self._tools.tool == ToolType.SELECT:
            self.delete_selection(); return

        # ── Undo / Redo ───────────────────────────────────────────────────────
        if ctrl and key == _Qt.Key.Key_Z:
            self.undo(); return
        if ctrl and (key == _Qt.Key.Key_Y or (shift and key == _Qt.Key.Key_Z)):
            self.redo(); return

        super().keyPressEvent(event)

    def leaveEvent(self, event):
        self._mouse_widget_pos = None
        self.update()

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        self._zoom = max(0.1, min(16.0, self._zoom * (1.1 if delta > 0 else 0.9)))
        self.update()

    # ── Drag & drop ───────────────────────────────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith((".png",".jpg",".jpeg",".bmp",".webp")):
                self._import_image(path)
                break

    def _import_image(self, path: str):
        """Import an image as a new layer with transform support."""
        try:
            img = Image.open(path).convert("RGBA")
            self._push_history()
            name = path.replace("\\", "/").split("/")[-1]
            new_layer = self._canvas.add_layer(f"Import: {name}")
            # Use set_source so the image is transform-editable immediately
            new_layer.set_source(img)
            self._invalidate_cache()
            self.canvas_changed.emit(self._canvas.flatten())
            # Auto-switch to transform tool
            self._tools.tool = ToolType.TRANSFORM
        except Exception as e:
            self.status_message.emit(f"Import failed: {e}")

    # ── Public helpers ────────────────────────────────────────────────────────

    def import_image_file(self, path: str):
        self._import_image(path)

    def flip_transform_h(self):
        layer = self._tx_layer()
        if layer:
            self._push_history()
            layer.transform.flip_h = not layer.transform.flip_h
            self._invalidate_cache()
            self.canvas_changed.emit(self._canvas.flatten())

    def flip_transform_v(self):
        layer = self._tx_layer()
        if layer:
            self._push_history()
            layer.transform.flip_v = not layer.transform.flip_v
            self._invalidate_cache()
            self.canvas_changed.emit(self._canvas.flatten())

    def reset_transform(self):
        layer = self._tx_layer()
        if layer:
            self._push_history()
            layer.transform = LayerTransform()
            self._invalidate_cache()
            self.canvas_changed.emit(self._canvas.flatten())

    # ── Private helpers ───────────────────────────────────────────────────────

    def _track_recent_color(self, color):
        """Add color to recent list (max 16, no duplicates)."""
        rc = self._tools.recent_colors
        key = (color.r, color.g, color.b, color.a)
        # Remove if already present
        self._tools.recent_colors = [c for c in rc
                                     if (c.r, c.g, c.b, c.a) != key]
        self._tools.recent_colors.insert(0, color)
        self._tools.recent_colors = self._tools.recent_colors[:16]
        self.recent_colors_changed.emit()

    def _canvas_changed_emit(self):
        self._invalidate_cache()
        self.canvas_changed.emit(self._canvas.flatten())

    def sync_text_settings(self):
        """Called whenever tool settings change — update the selected text object."""
        idx = self._active_text_idx
        if idx < 0:
            idx = self._last_text_idx
        if idx < 0 or idx >= len(self._text_objects):
            return
        obj = self._text_objects[idx]
        changed = (obj['font_name'] != self._tools.font_name or
                   obj['font_size'] != self._tools.font_size or
                   obj['color']     != self._tools.primary_color)
        obj['font_name'] = self._tools.font_name
        obj['font_size'] = self._tools.font_size
        obj['color']     = self._tools.primary_color
        if changed:
            self._cache_dirty = True
            self.update()

    def _text_hit(self, cx, cy):
        """Return index of text object under canvas point (cx,cy), or -1."""
        for i, obj in enumerate(self._text_objects):
            tw, th = measure_text(obj['text'], obj['font_name'], obj['font_size'])
            tw = max(tw, 20); th = max(th, obj['font_size'])
            if (obj['x'] <= cx <= obj['x'] + tw and
                    obj['y'] <= cy <= obj['y'] + th):
                return i
        return -1

    def _bake_text(self, idx):
        """Permanently render a text object into its layer pixels."""
        if idx < 0 or idx >= len(self._text_objects):
            return
        obj = self._text_objects[idx]
        li  = obj['layer_index']
        if 0 <= li < len(self._canvas.layers):
            layer = self._canvas.layers[li]
            if not layer.locked:
                self._push_history()
                draw_text(layer.pixels, obj['x'], obj['y'], obj['text'],
                          obj['color'], obj['font_name'], obj['font_size'])
                self.canvas_changed.emit(self._canvas.flatten())

    # ── Selection helpers ─────────────────────────────────────────────────────

    def get_selection_rect(self) -> Optional[Tuple[int,int,int,int]]:
        """Return (x, y, w, h) of current selection, or None for full canvas."""
        return self._selection

    def clear_selection(self):
        """Deselect / drop floating selection."""
        if self._sel_float is not None:
            self._flatten_float()
        self._selection    = None
        self._sel_dragging = False
        self._sel_float    = None
        self._invalidate_cache()

    def _flatten_float(self):
        """Stamp the floating pixels back into the active layer."""
        if self._sel_float is None:
            return
        layer = self._canvas.active_layer
        if layer is None:
            return
        fx, fy = self._sel_float_pos
        fh, fw = self._sel_float.shape[:2]
        h, w   = layer.pixels.shape[:2]
        x0, y0 = max(0, fx), max(0, fy)
        x1, y1 = min(w, fx+fw), min(h, fy+fh)
        if x1 > x0 and y1 > y0:
            sx0, sy0 = x0-fx, y0-fy
            from core.paint_engine import _composite as _comp
            patch = self._sel_float[sy0:sy0+(y1-y0), sx0:sx0+(x1-x0)]
            dest  = layer.pixels[y0:y1, x0:x1]
            # alpha-composite float over dest
            fa  = patch[...,3:].astype(np.float32)/255
            da  = dest[...,3:].astype(np.float32)/255
            oa  = fa + da*(1-fa)
            safe= np.where(oa>0, oa, 1.0)
            for i in range(3):
                dest[...,i] = np.clip(
                    (patch[...,i].astype(np.float32)*fa[...,0] +
                     dest[...,i].astype(np.float32)*da[...,0]*(1-fa[...,0])) / safe[...,0],
                    0, 255)
            dest[...,3] = np.clip(oa[...,0]*255, 0, 255)
            layer.pixels[y0:y1, x0:x1] = dest
        self._sel_float = None

    def copy_selection(self):
        """Copy selected region to clipboard (internal)."""
        layer = self._canvas.active_layer
        if layer is None:
            return
        if self._selection is None:
            self._sel_float     = layer.pixels.copy()
            self._sel_float_pos = (0, 0)
        else:
            x, y, w, h = self._selection
            self._sel_float     = layer.pixels[y:y+h, x:x+w].copy()
            self._sel_float_pos = (x, y)

    def cut_selection(self):
        """Cut selected region — lifts pixels into a floating layer."""
        layer = self._canvas.active_layer
        if layer is None:
            return
        self._push_history()
        self.copy_selection()
        if self._selection:
            x, y, w, h = self._selection
            layer.pixels[y:y+h, x:x+w] = 0   # erase source
        else:
            layer.pixels[:] = 0
        self._invalidate_cache()
        self.canvas_changed.emit(self._canvas.flatten())

    def paste_selection(self):
        """Paste the floating clipboard at current position."""
        if self._sel_float is None:
            return
        self._push_history()
        self._flatten_float()
        self._selection = None
        self._invalidate_cache()
        self.canvas_changed.emit(self._canvas.flatten())

    def delete_selection(self):
        """Delete (clear) the selected region."""
        layer = self._canvas.active_layer
        if layer is None:
            return
        self._push_history()
        if self._selection:
            x, y, w, h = self._selection
            layer.pixels[y:y+h, x:x+w, 3] = 0
        else:
            layer.pixels[..., 3] = 0
        self._invalidate_cache()
        self.canvas_changed.emit(self._canvas.flatten())

    def select_all(self):
        """Select entire canvas."""
        if self._sel_float is not None:
            self._flatten_float()
        self._selection = (0, 0, self._canvas.width, self._canvas.height)
        self._invalidate_cache()

    def _apply_brush(self, cx: int, cy: int):
        layer = self._canvas.active_layer
        if layer is None:
            return
        tool  = self._tools.tool
        bt    = getattr(self._tools, 'brush_type', None)
        prev  = self._last_canvas_pos
        px, py = (prev[0], prev[1]) if prev else (cx, cy)

        # Collect all (x, y, prev_x, prev_y) dab positions for symmetry
        W, H = self._canvas.width, self._canvas.height
        cx_m = W - 1 - cx;  px_m = W - 1 - px   # h-mirror
        cy_m = H - 1 - cy;  py_m = H - 1 - py   # v-mirror
        sym = getattr(self._tools, 'symmetry_axis', None)
        if sym is None:
            from core.models import SymmetryAxis as _SA
            sym = _SA.NONE
        from core.models import SymmetryAxis as _SA

        # Track this color as recently used
        self._track_recent_color(self._tools.primary_color)

        dabs = [(cx, cy, px, py)]
        if sym in (_SA.HORIZONTAL, _SA.BOTH):
            dabs.append((cx_m, cy, px_m, py))
        if sym in (_SA.VERTICAL, _SA.BOTH):
            dabs.append((cx, cy_m, px, py_m))
        if sym == _SA.BOTH:
            dabs.append((cx_m, cy_m, px_m, py_m))

        for dx, dy, dpx, dpy in dabs:
            if tool == ToolType.BRUSH:
                paint_brush_stroke(layer.pixels, dx, dy, self._tools.primary_color,
                                   self._tools.brush_size, self._tools.brush_hardness,
                                   self._tools.brush_opacity, bt, dpx, dpy, dx ^ dy)
            elif tool == ToolType.ERASER:
                erase_brush_stroke(layer.pixels, dx, dy,
                                   self._tools.brush_size, self._tools.brush_hardness,
                                   self._tools.brush_opacity)

        self._invalidate_cache()


    def _make_preview_flat(self, preview_pixels, target_layer) -> PILImage.Image:
        result = PILImage.new("RGBA", (self._canvas.width, self._canvas.height), (0,0,0,0))
        for layer in self._canvas.layers:
            if not layer.visible:
                continue
            if layer is target_layer:
                li = PILImage.fromarray(preview_pixels, "RGBA")
            elif layer.source_pixels is not None:
                raw = PILImage.fromarray(layer.source_pixels, "RGBA")
                li = layer.transform.apply_to_pil(raw, self._canvas.width, self._canvas.height)
            else:
                li = layer.to_pil()
            if layer.opacity < 1.0:
                r, g, b, a = li.split()
                a = a.point(lambda x: int(x * layer.opacity))
                li = PILImage.merge("RGBA", (r, g, b, a))
            result = PILImage.alpha_composite(result, li)
        return result


# ── Utilities ─────────────────────────────────────────────────────────────────

def _point_in_quad(px: float, py: float, corners) -> bool:
    """Test if point is inside a (possibly rotated) quadrilateral."""
    def cross(o, a, b):
        return (a.x()-o.x())*(b.y()-o.y()) - (a.y()-o.y())*(b.x()-o.x())
    pt = QPointF(px, py)
    tl, tr, br, bl = corners
    signs = [cross(tl, tr, pt), cross(tr, br, pt),
             cross(br, bl, pt), cross(bl, tl, pt)]
    return all(s >= 0 for s in signs) or all(s <= 0 for s in signs)


def _pil_to_pixmap(img: Image.Image) -> QPixmap:
    img  = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qi   = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qi)
