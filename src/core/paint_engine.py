"""
core/paint_engine.py - Low-level pixel painting operations.

All operations work directly on numpy RGBA uint8 arrays for
performance.  The public API matches the tools in ToolType and
is called by the canvas widget on mouse events.
"""

from __future__ import annotations

import math
from typing import Tuple, Optional, List

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from core.models import Color, Layer


# ─── Type aliases ────────────────────────────────────────────────────────────
Point = Tuple[int, int]
Pixels = np.ndarray   # shape (H, W, 4), dtype uint8


# ─── Brush ───────────────────────────────────────────────────────────────────

def paint_brush_stroke(
    pixels: Pixels,
    x: int,
    y: int,
    color: Color,
    size: int,
    hardness: float,
    opacity: float,
) -> None:
    """
    Paint a circular brush dab at (x, y) onto *pixels* in-place.

    Args:
        pixels:   RGBA numpy array to modify.
        x, y:     Centre of the dab in pixel coordinates.
        color:    Paint colour.
        size:     Diameter in pixels.
        hardness: 0.0 = completely soft (Gaussian falloff),
                  1.0 = hard edge.
        opacity:  Brush opacity 0.0–1.0.
    """
    h, w = pixels.shape[:2]
    radius = max(1, size // 2)

    # Bounding box (clamped to canvas)
    x0, x1 = max(0, x - radius), min(w, x + radius + 1)
    y0, y1 = max(0, y - radius), min(h, y + radius + 1)

    if x0 >= x1 or y0 >= y1:
        return

    # Build a per-pixel alpha mask
    ys, xs = np.mgrid[y0:y1, x0:x1]
    dist = np.sqrt((xs - x) ** 2 + (ys - y) ** 2).astype(np.float32)
    norm_dist = dist / max(radius, 1)

    if hardness >= 1.0:
        mask = (norm_dist <= 1.0).astype(np.float32)
    else:
        # Smooth falloff: linear between hardness radius and outer edge
        inner = hardness
        mask = np.clip((1.0 - norm_dist) / (1.0 - inner + 1e-6), 0.0, 1.0)
        mask *= (norm_dist <= 1.0)

    mask *= opacity * (color.a / 255.0)

    # Alpha-composite colour onto existing pixels
    src_r = np.float32(color.r)
    src_g = np.float32(color.g)
    src_b = np.float32(color.b)

    region = pixels[y0:y1, x0:x1].astype(np.float32) / 255.0
    dst_a = region[..., 3]
    src_a = mask

    out_a = src_a + dst_a * (1.0 - src_a)
    safe = np.where(out_a > 0, out_a, 1.0)

    out_r = (src_r / 255.0 * src_a + region[..., 0] * dst_a * (1.0 - src_a)) / safe
    out_g = (src_g / 255.0 * src_a + region[..., 1] * dst_a * (1.0 - src_a)) / safe
    out_b = (src_b / 255.0 * src_a + region[..., 2] * dst_a * (1.0 - src_a)) / safe

    pixels[y0:y1, x0:x1, 0] = np.clip(out_r * 255, 0, 255).astype(np.uint8)
    pixels[y0:y1, x0:x1, 1] = np.clip(out_g * 255, 0, 255).astype(np.uint8)
    pixels[y0:y1, x0:x1, 2] = np.clip(out_b * 255, 0, 255).astype(np.uint8)
    pixels[y0:y1, x0:x1, 3] = np.clip(out_a * 255, 0, 255).astype(np.uint8)


def paint_line(
    pixels: Pixels,
    p0: Point,
    p1: Point,
    color: Color,
    size: int,
    hardness: float,
    opacity: float,
) -> None:
    """
    Paint a continuous stroke from p0 to p1 by interpolating brush dabs.
    """
    x0, y0 = p0
    x1, y1 = p1
    dist = math.hypot(x1 - x0, y1 - y0)
    steps = max(1, int(dist))
    for i in range(steps + 1):
        t = i / steps
        x = int(x0 + t * (x1 - x0))
        y = int(y0 + t * (y1 - y0))
        paint_brush_stroke(pixels, x, y, color, size, hardness, opacity)


def erase_brush_stroke(
    pixels: Pixels,
    x: int,
    y: int,
    size: int,
    hardness: float,
    opacity: float,
) -> None:
    """Erase (reduce alpha) at the brush position."""
    h, w = pixels.shape[:2]
    radius = max(1, size // 2)
    x0, x1 = max(0, x - radius), min(w, x + radius + 1)
    y0, y1 = max(0, y - radius), min(h, y + radius + 1)

    if x0 >= x1 or y0 >= y1:
        return

    ys, xs = np.mgrid[y0:y1, x0:x1]
    dist = np.sqrt((xs - x) ** 2 + (ys - y) ** 2).astype(np.float32)
    norm_dist = dist / max(radius, 1)

    if hardness >= 1.0:
        mask = (norm_dist <= 1.0).astype(np.float32) * opacity
    else:
        inner = hardness
        mask_f = np.clip((1.0 - norm_dist) / (1.0 - inner + 1e-6), 0.0, 1.0)
        mask = mask_f * (norm_dist <= 1.0) * opacity

    pixels[y0:y1, x0:x1, 3] = np.clip(
        pixels[y0:y1, x0:x1, 3].astype(np.float32) * (1.0 - mask),
        0, 255
    ).astype(np.uint8)


# ─── Flood fill ──────────────────────────────────────────────────────────────

def flood_fill(
    pixels: Pixels,
    x: int,
    y: int,
    fill_color: Color,
    tolerance: int = 32,
) -> None:
    """
    Bucket-fill starting at (x, y) replacing pixels within *tolerance*
    of the seed colour with *fill_color*.  Uses iterative BFS.
    """
    h, w = pixels.shape[:2]
    if not (0 <= x < w and 0 <= y < h):
        return

    seed_color = pixels[y, x].copy()
    target = np.array([fill_color.r, fill_color.g, fill_color.b, fill_color.a], dtype=np.uint8)

    if np.array_equal(seed_color, target):
        return

    # Build boolean mask of pixels to fill using vectorised colour distance
    diff = pixels.astype(np.int32) - seed_color.astype(np.int32)
    dist = np.sqrt((diff ** 2).sum(axis=2))
    fillable = dist <= tolerance

    # BFS to find connected region
    visited = np.zeros((h, w), dtype=bool)
    queue = [(x, y)]
    visited[y, x] = True

    while queue:
        cx, cy = queue.pop()
        pixels[cy, cx] = target
        for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
            if 0 <= nx < w and 0 <= ny < h and not visited[ny, nx] and fillable[ny, nx]:
                visited[ny, nx] = True
                queue.append((nx, ny))


# ─── Shape tools ─────────────────────────────────────────────────────────────

def draw_rectangle(
    pixels: Pixels,
    x0: int, y0: int,
    x1: int, y1: int,
    color: Color,
    filled: bool = False,
    line_width: int = 2,
) -> None:
    """Draw a rectangle outline or filled rectangle."""
    img = Image.fromarray(pixels, "RGBA")
    draw = ImageDraw.Draw(img, "RGBA")
    c = color.to_tuple()
    rect = [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]
    if filled:
        draw.rectangle(rect, fill=c)
    else:
        draw.rectangle(rect, outline=c, width=line_width)
    pixels[:] = np.array(img)


def draw_ellipse(
    pixels: Pixels,
    x0: int, y0: int,
    x1: int, y1: int,
    color: Color,
    filled: bool = False,
    line_width: int = 2,
) -> None:
    """Draw an ellipse outline or filled ellipse."""
    img = Image.fromarray(pixels, "RGBA")
    draw = ImageDraw.Draw(img, "RGBA")
    c = color.to_tuple()
    rect = [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]
    if filled:
        draw.ellipse(rect, fill=c)
    else:
        draw.ellipse(rect, outline=c, width=line_width)
    pixels[:] = np.array(img)


def draw_line_shape(
    pixels: Pixels,
    x0: int, y0: int,
    x1: int, y1: int,
    color: Color,
    line_width: int = 2,
) -> None:
    """Draw a straight line."""
    img = Image.fromarray(pixels, "RGBA")
    draw = ImageDraw.Draw(img, "RGBA")
    draw.line([x0, y0, x1, y1], fill=color.to_tuple(), width=line_width)
    pixels[:] = np.array(img)


# ─── Text tool ───────────────────────────────────────────────────────────────

def draw_text(
    pixels: Pixels,
    x: int,
    y: int,
    text: str,
    color: Color,
    font_name: str = "Arial",
    font_size: int = 24,
) -> None:
    """Render *text* onto *pixels* at position (x, y)."""
    img = Image.fromarray(pixels, "RGBA")
    draw = ImageDraw.Draw(img, "RGBA")
    try:
        font = ImageFont.truetype(font_name, font_size)
    except (OSError, IOError):
        font = ImageFont.load_default()
    draw.text((x, y), text, fill=color.to_tuple(), font=font)
    pixels[:] = np.array(img)


# ─── Eyedropper ──────────────────────────────────────────────────────────────

def pick_color(pixels: Pixels, x: int, y: int) -> Optional[Color]:
    """Return the colour of the pixel at (x, y), or None if out of bounds."""
    h, w = pixels.shape[:2]
    if not (0 <= x < w and 0 <= y < h):
        return None
    r, g, b, a = pixels[y, x]
    return Color(int(r), int(g), int(b), int(a))


# ─── Transform helpers ───────────────────────────────────────────────────────

def resize_layer_pixels(pixels: Pixels, new_w: int, new_h: int) -> Pixels:
    """Resize pixel data to new dimensions using LANCZOS resampling."""
    img = Image.fromarray(pixels, "RGBA")
    img = img.resize((new_w, new_h), Image.LANCZOS)
    return np.array(img, dtype=np.uint8)


def rotate_layer_pixels(pixels: Pixels, angle: float, expand: bool = False) -> Pixels:
    """Rotate pixel data by *angle* degrees counter-clockwise."""
    img = Image.fromarray(pixels, "RGBA")
    img = img.rotate(angle, expand=expand, resample=Image.BICUBIC)
    return np.array(img, dtype=np.uint8)


def crop_layer_pixels(pixels: Pixels, x0: int, y0: int, x1: int, y1: int) -> Pixels:
    """Crop pixel data to the given rectangle."""
    img = Image.fromarray(pixels, "RGBA")
    img = img.crop((x0, y0, x1, y1))
    return np.array(img, dtype=np.uint8)
