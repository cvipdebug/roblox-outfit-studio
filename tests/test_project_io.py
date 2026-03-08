"""
tests/test_project_io.py - Tests for project save / load / export.
"""

import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
import numpy as np

from core.models import CanvasState, Color, BlendMode
from core.project_io import (
    save_project, load_project, export_texture, export_template_png,
    PROJECT_EXTENSION,
)


class TestProjectIO:
    def _make_canvas(self) -> CanvasState:
        canvas = CanvasState(width=64, height=64)
        bg = canvas.add_layer("Background")
        bg.fill(Color(100, 150, 200, 255))
        layer2 = canvas.add_layer("Overlay")
        layer2.opacity = 0.5
        layer2.blend_mode = BlendMode.MULTIPLY
        layer2.pixels[10:20, 10:20] = [255, 0, 0, 255]
        return canvas

    def test_save_creates_file(self):
        canvas = self._make_canvas()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test_project")
            save_project(canvas, path)
            assert os.path.exists(path + PROJECT_EXTENSION)

    def test_save_load_roundtrip(self):
        canvas = self._make_canvas()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.outfitproj")
            save_project(canvas, path)
            loaded = load_project(path)

            assert loaded.width == canvas.width
            assert loaded.height == canvas.height
            assert len(loaded.layers) == len(canvas.layers)
            assert loaded.layers[0].name == "Background"
            assert loaded.layers[1].name == "Overlay"
            assert abs(loaded.layers[1].opacity - 0.5) < 0.01
            assert loaded.layers[1].blend_mode == BlendMode.MULTIPLY

    def test_pixel_data_preserved(self):
        canvas = self._make_canvas()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.outfitproj")
            save_project(canvas, path)
            loaded = load_project(path)
            np.testing.assert_array_equal(
                loaded.layers[0].pixels,
                canvas.layers[0].pixels,
            )

    def test_load_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_project("/nonexistent/path.outfitproj")

    def test_export_texture(self):
        canvas = self._make_canvas()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "texture.png")
            export_texture(canvas, out, "shirt")
            assert os.path.exists(out)
            from PIL import Image
            img = Image.open(out)
            # Should be resized to Roblox shirt dimensions
            assert img.size == (585, 559)

    def test_export_template_shirt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "template.png")
            export_template_png("shirt", out)
            assert os.path.exists(out)
            from PIL import Image
            img = Image.open(out)
            assert img.size == (585, 559)

    def test_export_template_pants(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "template.png")
            export_template_png("pants", out)
            assert os.path.exists(out)

    def test_active_layer_index_preserved(self):
        canvas = self._make_canvas()
        canvas.active_layer_index = 1
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.outfitproj")
            save_project(canvas, path, project_name="MyProject")
            loaded = load_project(path)
            assert loaded.active_layer_index == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
