"""
core/project_io.py - Save and load project files.

Projects are stored as .outfitproj files which are ZIP archives
containing:
  - project.json   (metadata, layer config)
  - layer_<id>.png (per-layer pixel data)
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from typing import Optional

import numpy as np
from PIL import Image

from core.models import CanvasState, Layer, BlendMode, ProjectFile, TEMPLATE_SIZES


PROJECT_EXTENSION = ".outfitproj"
META_FILENAME = "project.json"
FORMAT_VERSION = "1.0"


def save_project(canvas: CanvasState, file_path: str, project_name: str = "Untitled") -> None:
    """
    Serialise *canvas* to a ``.outfitproj`` ZIP archive at *file_path*.

    Args:
        canvas:       The canvas state to save.
        file_path:    Destination path (extension added if missing).
        project_name: Human-readable project name stored in metadata.
    """
    if not file_path.endswith(PROJECT_EXTENSION):
        file_path += PROJECT_EXTENSION

    meta: dict = {
        "version": FORMAT_VERSION,
        "name": project_name,
        "canvas_width": canvas.width,
        "canvas_height": canvas.height,
        "active_layer_index": canvas.active_layer_index,
        "layers": [],
    }

    with zipfile.ZipFile(file_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for layer in canvas.layers:
            layer_entry = {
                "id": layer.layer_id,
                "name": layer.name,
                "visible": layer.visible,
                "opacity": layer.opacity,
                "blend_mode": layer.blend_mode.value,
                "locked": layer.locked,
            }
            meta["layers"].append(layer_entry)

            # Save pixel data as PNG
            img = Image.fromarray(layer.pixels, "RGBA")
            buf = io.BytesIO()
            img.save(buf, format="PNG", compress_level=6)
            zf.writestr(f"layer_{layer.layer_id}.png", buf.getvalue())

        zf.writestr(META_FILENAME, json.dumps(meta, indent=2))


def load_project(file_path: str) -> CanvasState:
    """
    Load a ``.outfitproj`` file and return a populated ``CanvasState``.

    Raises:
        FileNotFoundError: if *file_path* does not exist.
        ValueError:        if the file format is unrecognised.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Project file not found: {file_path}")

    with zipfile.ZipFile(file_path, "r") as zf:
        names = zf.namelist()
        if META_FILENAME not in names:
            raise ValueError("Invalid project file: missing project.json")

        meta = json.loads(zf.read(META_FILENAME).decode("utf-8"))

        canvas = CanvasState(
            width=meta.get("canvas_width", 585),
            height=meta.get("canvas_height", 559),
        )
        canvas.active_layer_index = meta.get("active_layer_index", 0)
        canvas.layers.clear()

        for layer_entry in meta.get("layers", []):
            lid = layer_entry["id"]
            png_name = f"layer_{lid}.png"

            if png_name in names:
                img_data = zf.read(png_name)
                img = Image.open(io.BytesIO(img_data)).convert("RGBA")
                pixels = np.array(img, dtype=np.uint8)
            else:
                pixels = np.zeros((canvas.height, canvas.width, 4), dtype=np.uint8)

            layer = Layer(
                name=layer_entry.get("name", "Layer"),
                width=canvas.width,
                height=canvas.height,
                layer_id=lid,
                visible=layer_entry.get("visible", True),
                opacity=layer_entry.get("opacity", 1.0),
                blend_mode=BlendMode(layer_entry.get("blend_mode", "normal")),
                locked=layer_entry.get("locked", False),
                pixels=pixels,
            )
            canvas.layers.append(layer)

    if not canvas.layers:
        canvas.add_layer("Background")

    return canvas


def export_texture(canvas: CanvasState, file_path: str, template_type: str = "shirt") -> None:
    """
    Flatten canvas and export as a Roblox-ready PNG texture.

    Args:
        canvas:        The canvas to export.
        file_path:     Output PNG path.
        template_type: ``"shirt"``, ``"pants"``, or ``"custom"``.
                       The output is resized to the Roblox standard
                       dimensions for the chosen template.
    """
    flat = canvas.flatten()
    target_size = TEMPLATE_SIZES.get(template_type, (585, 559))
    if flat.size != target_size:
        flat = flat.resize(target_size, Image.LANCZOS)
    flat.save(file_path, format="PNG")


def export_template_png(template_type: str, output_path: str) -> None:
    """
    Write a blank Roblox clothing template guide PNG to *output_path*.

    The template shows seam guides on a transparent background so the
    user can see exactly where to paint shirt/pants sections.
    """
    w, h = TEMPLATE_SIZES.get(template_type, (585, 559))
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)

    if template_type == "shirt":
        _draw_shirt_guide(draw, w, h)
    elif template_type == "pants":
        _draw_pants_guide(draw, w, h)

    img.save(output_path, format="PNG")


def _draw_shirt_guide(draw: "ImageDraw.ImageDraw", w: int, h: int) -> None:
    """Draw Roblox shirt template seam guides."""
    guide = (100, 180, 255, 80)
    outline = (100, 180, 255, 160)

    # Approximate Roblox shirt UV regions
    regions = {
        "Torso Front":  (102, 234, 204, 338),
        "Torso Back":   (205, 234, 307, 338),
        "Left Arm":     (0,   234, 101, 338),
        "Right Arm":    (308, 234, 409, 338),
        "Left Sleeve":  (0,   339, 98,  443),
        "Right Sleeve": (308, 339, 406, 443),
    }
    try:
        from PIL import ImageFont
        font = ImageFont.load_default()
    except Exception:
        font = None

    for label, (x0, y0, x1, y1) in regions.items():
        draw.rectangle([x0, y0, x1, y1], fill=guide, outline=outline, width=2)
        draw.text((x0 + 4, y0 + 4), label, fill=(200, 220, 255, 200), font=font)


def _draw_pants_guide(draw: "ImageDraw.ImageDraw", w: int, h: int) -> None:
    """Draw Roblox pants template seam guides."""
    guide = (180, 255, 100, 80)
    outline = (180, 255, 100, 160)

    regions = {
        "Left Leg Front":  (0,   0,   196, 480),
        "Right Leg Front": (200, 0,   396, 480),
        "Waist":           (0,   481, 196, 558),
    }
    try:
        from PIL import ImageFont
        font = ImageFont.load_default()
    except Exception:
        font = None

    for label, (x0, y0, x1, y1) in regions.items():
        draw.rectangle([x0, y0, x1, y1], fill=guide, outline=outline, width=2)
        draw.text((x0 + 4, y0 + 4), label, fill=(220, 255, 200, 200), font=font)
