"""
tests/test_core.py - Unit tests for core data models, history, and paint engine.

Run with: python -m pytest tests/ -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
import numpy as np
from PIL import Image

from core.models import (
    Color, Layer, CanvasState, BlendMode, ToolSettings, ToolType, TEMPLATE_SIZES
)
from core.history import HistoryManager
from core.paint_engine import (
    paint_brush_stroke, flood_fill, draw_rectangle,
    draw_ellipse, draw_line_shape, pick_color,
    resize_layer_pixels, rotate_layer_pixels,
)


# ── Color tests ──────────────────────────────────────────────────────────────

class TestColor:
    def test_to_tuple(self):
        c = Color(255, 128, 0, 200)
        assert c.to_tuple() == (255, 128, 0, 200)

    def test_to_hex(self):
        c = Color(255, 0, 128)
        assert c.to_hex() == "#FF0080"

    def test_from_hex(self):
        c = Color.from_hex("#FF0080")
        assert c.r == 255 and c.g == 0 and c.b == 128

    def test_from_tuple(self):
        c = Color.from_tuple((10, 20, 30, 40))
        assert c.r == 10 and c.a == 40


# ── Layer tests ───────────────────────────────────────────────────────────────

class TestLayer:
    def test_creation_transparent(self):
        layer = Layer("Test", 100, 100)
        assert layer.pixels.shape == (100, 100, 4)
        assert layer.pixels.sum() == 0   # fully transparent

    def test_fill(self):
        layer = Layer("Test", 10, 10)
        layer.fill(Color(255, 0, 0, 255))
        assert layer.pixels[0, 0, 0] == 255
        assert layer.pixels[0, 0, 3] == 255

    def test_clear(self):
        layer = Layer("Test", 10, 10)
        layer.fill(Color(255, 0, 0, 255))
        layer.clear()
        assert layer.pixels.sum() == 0

    def test_clone(self):
        layer = Layer("Original", 20, 20)
        layer.fill(Color(0, 255, 0, 255))
        clone = layer.clone()
        assert clone.layer_id != layer.layer_id
        assert clone.name == "Original copy"
        np.testing.assert_array_equal(clone.pixels, layer.pixels)
        # Ensure deep copy
        clone.pixels[0, 0, 0] = 0
        assert layer.pixels[0, 0, 0] == 0

    def test_to_pil(self):
        layer = Layer("Test", 50, 50)
        img = layer.to_pil()
        assert isinstance(img, Image.Image)
        assert img.size == (50, 50)
        assert img.mode == "RGBA"

    def test_from_pil(self):
        layer = Layer("Test", 50, 50)
        img = Image.new("RGB", (100, 100), (128, 64, 32))
        layer.from_pil(img)
        assert layer.pixels.shape == (50, 50, 4)


# ── CanvasState tests ─────────────────────────────────────────────────────────

class TestCanvasState:
    def test_add_layer(self):
        canvas = CanvasState(100, 100)
        layer = canvas.add_layer("BG")
        assert len(canvas.layers) == 1
        assert canvas.active_layer is layer

    def test_remove_layer(self):
        canvas = CanvasState(100, 100)
        canvas.add_layer("L1")
        canvas.add_layer("L2")
        canvas.remove_layer(1)
        assert len(canvas.layers) == 1

    def test_remove_last_layer_noop(self):
        canvas = CanvasState(100, 100)
        canvas.add_layer("only")
        canvas.remove_layer(0)
        assert len(canvas.layers) == 1

    def test_move_layer(self):
        canvas = CanvasState(100, 100)
        l1 = canvas.add_layer("L1")
        l2 = canvas.add_layer("L2")
        canvas.move_layer(0, 1)
        assert canvas.layers[0] is l2

    def test_flatten_empty(self):
        canvas = CanvasState(50, 50)
        canvas.add_layer("BG")
        flat = canvas.flatten()
        assert flat.size == (50, 50)

    def test_flatten_with_colour(self):
        canvas = CanvasState(10, 10)
        layer = canvas.add_layer("L")
        layer.fill(Color(255, 0, 0, 255))
        flat = canvas.flatten()
        px = flat.getpixel((0, 0))
        assert px[0] == 255 and px[1] == 0

    def test_flatten_invisible_layer_excluded(self):
        canvas = CanvasState(10, 10)
        layer = canvas.add_layer("L")
        layer.fill(Color(255, 0, 0, 255))
        layer.visible = False
        flat = canvas.flatten()
        px = flat.getpixel((0, 0))
        assert px[3] == 0

    def test_snapshot(self):
        canvas = CanvasState(10, 10)
        layer = canvas.add_layer("L")
        layer.fill(Color(1, 2, 3, 255))
        snap = canvas.snapshot()
        layer.fill(Color(100, 100, 100, 255))
        assert snap.layers[0].pixels[0, 0, 0] == 1   # Snapshot unaffected


# ── HistoryManager tests ──────────────────────────────────────────────────────

class TestHistoryManager:
    def _make_canvas(self, color: int) -> CanvasState:
        canvas = CanvasState(10, 10)
        layer = canvas.add_layer("L")
        layer.fill(Color(color, 0, 0, 255))
        return canvas

    def test_undo_restores_state(self):
        hist = HistoryManager()
        c1 = self._make_canvas(10)
        hist.push(c1)
        c2 = self._make_canvas(20)
        restored = hist.undo(c2)
        assert restored is not None
        assert restored.layers[0].pixels[0, 0, 0] == 10

    def test_redo_after_undo(self):
        hist = HistoryManager()
        c1 = self._make_canvas(10)
        hist.push(c1)
        c2 = self._make_canvas(20)
        undone = hist.undo(c2)
        redone = hist.redo(undone)
        assert redone is not None
        assert redone.layers[0].pixels[0, 0, 0] == 20

    def test_push_clears_redo(self):
        hist = HistoryManager()
        c1 = self._make_canvas(10)
        hist.push(c1)
        c2 = self._make_canvas(20)
        hist.undo(c2)
        assert hist.can_redo
        hist.push(c2)
        assert not hist.can_redo

    def test_max_steps_respected(self):
        hist = HistoryManager(max_steps=3)
        for i in range(5):
            hist.push(self._make_canvas(i * 10))
        assert hist.undo_count == 3

    def test_undo_empty_returns_none(self):
        hist = HistoryManager()
        assert hist.undo(self._make_canvas(0)) is None

    def test_redo_empty_returns_none(self):
        hist = HistoryManager()
        assert hist.redo(self._make_canvas(0)) is None


# ── Paint engine tests ────────────────────────────────────────────────────────

class TestPaintEngine:
    def _empty(self, w=50, h=50) -> np.ndarray:
        return np.zeros((h, w, 4), dtype=np.uint8)

    def test_brush_stroke_paints(self):
        px = self._empty()
        paint_brush_stroke(px, 25, 25, Color(255, 0, 0, 255), 10, 1.0, 1.0)
        # Centre pixel should be red and opaque
        assert px[25, 25, 0] > 200
        assert px[25, 25, 3] > 200

    def test_brush_stroke_out_of_bounds_noop(self):
        px = self._empty()
        original = px.copy()
        paint_brush_stroke(px, -100, -100, Color(255, 0, 0, 255), 10, 1.0, 1.0)
        np.testing.assert_array_equal(px, original)

    def test_flood_fill_basic(self):
        px = self._empty(20, 20)
        flood_fill(px, 10, 10, Color(0, 0, 255, 255), tolerance=10)
        # Most pixels should now be blue
        blue_count = (px[:, :, 2] == 255).sum()
        assert blue_count > 300  # large area filled

    def test_flood_fill_respects_boundary(self):
        px = self._empty(20, 20)
        # Draw a red box that isolates a region
        px[5, :, :] = [255, 0, 0, 255]
        px[15, :, :] = [255, 0, 0, 255]
        # Fill inside the box
        flood_fill(px, 10, 10, Color(0, 0, 255, 255), tolerance=5)
        # Pixels above row 5 should not be blue
        assert px[2, 10, 2] == 0

    def test_draw_rectangle(self):
        px = self._empty()
        draw_rectangle(px, 5, 5, 20, 20, Color(0, 255, 0, 255))
        # A corner pixel should be painted
        assert px[5, 5, 1] > 0

    def test_draw_ellipse(self):
        px = self._empty()
        draw_ellipse(px, 5, 5, 45, 45, Color(255, 255, 0, 255))
        total_painted = (px[:, :, 3] > 0).sum()
        assert total_painted > 0

    def test_pick_color(self):
        px = self._empty()
        px[10, 10] = [1, 2, 3, 255]
        c = pick_color(px, 10, 10)
        assert c is not None
        assert c.r == 1 and c.g == 2 and c.b == 3

    def test_pick_color_out_of_bounds(self):
        px = self._empty()
        assert pick_color(px, 100, 100) is None

    def test_resize_layer(self):
        px = np.zeros((50, 100, 4), dtype=np.uint8)
        resized = resize_layer_pixels(px, 25, 10)
        assert resized.shape == (10, 25, 4)

    def test_rotate_layer(self):
        px = np.zeros((50, 50, 4), dtype=np.uint8)
        px[10, 10] = [255, 0, 0, 255]
        rotated = rotate_layer_pixels(px, 90)
        assert rotated.shape == (50, 50, 4)


# ── Template size constants ───────────────────────────────────────────────────

class TestTemplateConstants:
    def test_shirt_size(self):
        assert TEMPLATE_SIZES["shirt"] == (585, 559)

    def test_pants_size(self):
        assert TEMPLATE_SIZES["pants"] == (585, 559)

    def test_all_types_present(self):
        for key in ("shirt", "pants", "face", "custom"):
            assert key in TEMPLATE_SIZES


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
