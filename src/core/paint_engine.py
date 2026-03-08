"""
core/paint_engine.py - Low-level pixel painting operations.
20 visually distinct brush types, flood fill, shapes, text.
"""
from __future__ import annotations
import math
from typing import Tuple, Optional
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from core.models import Color, Layer, BrushType

Point  = Tuple[int, int]
Pixels = np.ndarray   # (H, W, 4) uint8

# ─── Internal helpers ────────────────────────────────────────────────────────

def _clamp_bbox(x, y, r, w, h):
    x, y = int(x), int(y)
    x0, x1 = max(0, x - r - 1), min(w, x + r + 2)
    y0, y1 = max(0, y - r - 1), min(h, y + r + 2)
    return x0, y0, x1, y1

def _circular_mask(x, y, pixels, radius, hardness, opacity=1.0):
    """Circular alpha mask. radius is actual radius (not size)."""
    h, w = pixels.shape[:2]
    x0, y0, x1, y1 = _clamp_bbox(x, y, int(radius) + 1, w, h)
    if x0 >= x1 or y0 >= y1:
        return y0, x0, None
    ys, xs = np.mgrid[y0:y1, x0:x1]
    dist = np.sqrt((xs - x) ** 2 + (ys - y) ** 2).astype(np.float32)
    norm = dist / max(radius, 1e-6)
    if hardness >= 1.0:
        mask = (norm <= 1.0).astype(np.float32)
    else:
        inner = max(0.0, hardness)
        mask = np.clip((1.0 - norm) / (1.0 - inner + 1e-6), 0.0, 1.0) * (norm <= 1.0)
    return y0, x0, mask * opacity

def _flat_mask(x, y, pixels, half_w, half_h, angle_deg=0.0, opacity=1.0):
    """Flat rectangular mask, optionally rotated."""
    x, y = int(x), int(y)
    h, w = pixels.shape[:2]
    r = int(math.sqrt(half_w**2 + half_h**2)) + 2
    x0, y0, x1, y1 = _clamp_bbox(x, y, r, w, h)
    if x0 >= x1 or y0 >= y1:
        return y0, x0, None
    ys, xs = np.mgrid[y0:y1, x0:x1]
    ang = math.radians(angle_deg)
    ca, sa = math.cos(ang), math.sin(ang)
    lx =  (xs - x) * ca + (ys - y) * sa
    ly = -(xs - x) * sa + (ys - y) * ca
    mask = ((np.abs(lx) <= half_w) & (np.abs(ly) <= half_h)).astype(np.float32) * opacity
    return y0, x0, mask

def _composite(pixels, y0, x0, mask, color):
    """Alpha-composite a mask+color onto pixels."""
    if mask is None or mask.max() == 0:
        return
    y1, x1 = y0 + mask.shape[0], x0 + mask.shape[1]
    region = pixels[y0:y1, x0:x1].astype(np.float32) / 255.0
    src_a  = mask * (color.a / 255.0)
    dst_a  = region[..., 3]
    out_a  = src_a + dst_a * (1.0 - src_a)
    safe   = np.where(out_a > 0, out_a, 1.0)
    for i, val in enumerate((color.r, color.g, color.b)):
        out = (val / 255.0 * src_a + region[..., i] * dst_a * (1.0 - src_a)) / safe
        pixels[y0:y1, x0:x1, i] = np.clip(out * 255, 0, 255).astype(np.uint8)
    pixels[y0:y1, x0:x1, 3] = np.clip(out_a * 255, 0, 255).astype(np.uint8)

def _erase(pixels, y0, x0, mask):
    """Erase alpha using mask."""
    if mask is None:
        return
    y1, x1 = y0 + mask.shape[0], x0 + mask.shape[1]
    pixels[y0:y1, x0:x1, 3] = np.clip(
        pixels[y0:y1, x0:x1, 3].astype(np.float32) * (1.0 - mask), 0, 255
    ).astype(np.uint8)

def _smudge(pixels, x, y, size, strength, dx, dy):
    x, y = int(x), int(y)
    h, w = pixels.shape[:2]
    r  = max(1, size // 2)
    ox = int(dx * r * 0.5)
    oy = int(dy * r * 0.5)
    x0, x1 = max(0, x - r), min(w, x + r)
    y0, y1 = max(0, y - r), min(h, y + r)
    sx0 = max(0, x0 - ox); sy0 = max(0, y0 - oy)
    sx1 = min(w, x1 - ox); sy1 = min(h, y1 - oy)
    rw = min(x1 - x0, sx1 - sx0)
    rh = min(y1 - y0, sy1 - sy0)
    if rw <= 0 or rh <= 0:
        return
    dst = pixels[y0:y0+rh, x0:x0+rw].astype(np.float32)
    src = pixels[sy0:sy0+rh, sx0:sx0+rw].astype(np.float32)
    pixels[y0:y0+rh, x0:x0+rw] = np.clip(
        dst * (1.0 - strength) + src * strength, 0, 255
    ).astype(np.uint8)

def _blur_region(pixels, x, y, size, strength):
    x, y = int(x), int(y)
    h, w = pixels.shape[:2]
    r  = max(2, size // 2)
    x0, x1 = max(0, x - r), min(w, x + r)
    y0, y1 = max(0, y - r), min(h, y + r)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return
    patch   = Image.fromarray(pixels[y0:y1, x0:x1], 'RGBA')
    blurred = patch.filter(ImageFilter.GaussianBlur(radius=max(1, size * 0.12)))
    orig    = pixels[y0:y1, x0:x1].astype(np.float32)
    pixels[y0:y1, x0:x1] = np.clip(
        orig * (1 - strength) + np.array(blurred).astype(np.float32) * strength,
        0, 255
    ).astype(np.uint8)

def _varied_noise(shape, seed):
    """Noise that changes every dab by using a hash of position+stroke."""
    rng = np.random.RandomState(seed & 0xFFFFFFFF)
    return rng.rand(*shape).astype(np.float32)

# ─── Main brush dab ──────────────────────────────────────────────────────────

def paint_brush_dab(pixels, x, y, color, size, hardness, opacity, brush_type,
                    prev_x=None, prev_y=None, stroke_seed=0):
    """Paint one dab of brush_type at (x,y)."""
    dx = (x - prev_x) if prev_x is not None else 0
    dy = (y - prev_y) if prev_y is not None else 0
    angle = math.degrees(math.atan2(dy, dx)) if (dx or dy) else 0
    bt = brush_type
    radius = max(1.0, size / 2.0)
    # Unique seed per dab: mix position with stroke counter
    seed = abs(int(x * 73856093) ^ int(y * 19349663) ^ int(stroke_seed * 83492791))

    # ── Erasers ──────────────────────────────────────────────────────────────
    if bt == BrushType.ERASER_HARD:
        y0, x0, mask = _circular_mask(x, y, pixels, radius, 1.0, opacity)
        _erase(pixels, y0, x0, mask)
        return
    if bt == BrushType.ERASER_SOFT:
        y0, x0, mask = _circular_mask(x, y, pixels, radius, max(0.0, hardness * 0.3), opacity * 0.85)
        _erase(pixels, y0, x0, mask)
        return

    # ── Smudge ────────────────────────────────────────────────────────────────
    if bt == BrushType.SMUDGE:
        dist = math.hypot(dx, dy) + 1e-6
        _smudge(pixels, x, y, size, min(0.85, opacity), dx/dist, dy/dist)
        return

    # ── Blend ─────────────────────────────────────────────────────────────────
    if bt == BrushType.BLEND:
        _blur_region(pixels, x, y, size, min(0.9, opacity * 0.9))
        return

    # ── Flat / Calligraphy ────────────────────────────────────────────────────
    if bt == BrushType.FLAT:
        hw = max(1, size // 2); hh = max(1, size // 8)
        y0, x0, mask = _flat_mask(x, y, pixels, hw, hh, angle, opacity)
        _composite(pixels, y0, x0, mask, color)
        return
    if bt == BrushType.CALLIGRAPHY:
        hw = max(1, size // 2); hh = max(1, size // 10)
        y0, x0, mask = _flat_mask(x, y, pixels, hw, hh, 45.0, opacity * 0.92)
        _composite(pixels, y0, x0, mask, color)
        return

    # ── Hard Round ────────────────────────────────────────────────────────────
    if bt == BrushType.HARD_ROUND:
        y0, x0, mask = _circular_mask(x, y, pixels, radius, 1.0, opacity)
        _composite(pixels, y0, x0, mask, color)
        return

    # ── Soft Round ────────────────────────────────────────────────────────────
    if bt == BrushType.SOFT_ROUND:
        y0, x0, mask = _circular_mask(x, y, pixels, radius, max(0.0, hardness * 0.45), opacity)
        _composite(pixels, y0, x0, mask, color)
        return

    # ── Airbrush: very large soft falloff, low opacity per dab ───────────────
    if bt == BrushType.AIRBRUSH:
        y0, x0, mask = _circular_mask(x, y, pixels, radius * 1.5, 0.0, opacity * 0.18)
        _composite(pixels, y0, x0, mask, color)
        return

    # ── Pencil: hard edge with slight grain along the edge ───────────────────
    if bt == BrushType.PENCIL:
        y0, x0, mask = _circular_mask(x, y, pixels, radius, 0.85, opacity * 0.82)
        if mask is not None:
            noise = _varied_noise(mask.shape, seed)
            # Only add noise near the outer edge (norm > 0.65)
            h_w = pixels.shape[:2]
            ys, xs = np.mgrid[y0:y0+mask.shape[0], x0:x0+mask.shape[1]]
            dist = np.sqrt((xs - x)**2 + (ys - y)**2).astype(np.float32) / radius
            edge_noise = np.where(dist > 0.65, noise * 0.4, 0.0)
            mask = np.clip(mask - edge_noise, 0, 1)
        _composite(pixels, y0, x0, mask, color)
        return

    # ── Ink: perfectly hard, tapers to a point at stroke ends ────────────────
    if bt == BrushType.INK:
        y0, x0, mask = _circular_mask(x, y, pixels, radius, 1.0, opacity)
        _composite(pixels, y0, x0, mask, color)
        return

    # ── Chalk: coarse random grain, many gaps, medium opacity ────────────────
    if bt == BrushType.CHALK:
        y0, x0, mask = _circular_mask(x, y, pixels, radius, 0.8, opacity * 0.85)
        if mask is not None:
            # Dense random noise — ~35% pixels shown, rest transparent
            noise = _varied_noise(mask.shape, seed)
            grain = (noise < 0.35).astype(np.float32)
            # Also add coarser grain at a bigger scale
            noise2 = _varied_noise(mask.shape, seed + 1)
            coarse = (noise2 < 0.55).astype(np.float32)
            mask = mask * grain * coarse
        _composite(pixels, y0, x0, mask, color)
        return

    # ── Charcoal: smeared streaky grain, wider marks ─────────────────────────
    if bt == BrushType.CHARCOAL:
        y0, x0, mask = _circular_mask(x, y, pixels, radius * 1.1, 0.6, opacity * 0.70)
        if mask is not None:
            noise = _varied_noise(mask.shape, seed)
            # Streaky: keep mostly horizontal runs
            streak = (noise < 0.50).astype(np.float32)
            # Smear the streak horizontally for charcoal drag effect
            streak = np.maximum(streak, np.roll(streak, 2, axis=1) * 0.6)
            streak = np.maximum(streak, np.roll(streak, -2, axis=1) * 0.6)
            mask = mask * streak
            # Slight blur to soften edges
            if mask.shape[0] > 2 and mask.shape[1] > 2:
                from PIL import Image as _PIL
                m_img = _PIL.fromarray((mask * 255).astype(np.uint8), 'L')
                mask  = np.array(m_img.filter(ImageFilter.GaussianBlur(0.6))) / 255.0
        _composite(pixels, y0, x0, mask, color)
        return

    # ── Marker: flat full opacity, hard edge, slight overlap buildup ─────────
    if bt == BrushType.MARKER:
        y0, x0, mask = _circular_mask(x, y, pixels, radius, 0.95, min(1.0, opacity * 1.0))
        if mask is not None:
            # Marker doesn't darken already-painted areas — cap at color opacity
            mask = np.where(mask > 0, min(1.0, opacity), 0.0).astype(np.float32)
        _composite(pixels, y0, x0, mask, color)
        return

    # ── Watercolor: soft irregular edge with color bleed ─────────────────────
    if bt == BrushType.WATERCOLOR:
        y0, x0, mask = _circular_mask(x, y, pixels, radius, 0.05, opacity * 0.45)
        if mask is not None:
            noise = _varied_noise(mask.shape, seed)
            # Irregular soft boundary
            edge_var = 0.4 + 0.6 * noise
            mask = mask * edge_var
        _blur_region(pixels, x, y, max(2, size // 3), 0.08)
        _composite(pixels, y0, x0, mask, color)
        return

    # ── Oil: thick opaque dabs with slight directional smear ─────────────────
    if bt == BrushType.OIL:
        y0, x0, mask = _circular_mask(x, y, pixels, radius, 0.7, opacity)
        if mask is not None:
            noise = _varied_noise(mask.shape, seed)
            # Thick texture: nearly full coverage with slight variation
            thick = 0.75 + 0.25 * noise
            mask = mask * thick
        if abs(dx) + abs(dy) > 0.5:
            dist = math.hypot(dx, dy) + 1e-6
            _smudge(pixels, x, y, max(2, size // 4), 0.18, dx/dist, dy/dist)
        _composite(pixels, y0, x0, mask, color)
        return

    # ── Dry Brush: streaky with many bare patches, shows through ─────────────
    if bt == BrushType.DRY_BRUSH:
        y0, x0, mask = _circular_mask(x, y, pixels, radius, 0.75, opacity * 0.75)
        if mask is not None:
            noise  = _varied_noise(mask.shape, seed)
            noise2 = _varied_noise(mask.shape, seed + 7)
            # Sparse patches (40% shown) with directional streaks
            sparse = (noise < 0.40).astype(np.float32)
            streak = (noise2 < 0.60).astype(np.float32)
            # Elongate streaks in direction of stroke
            streak = np.maximum(streak, np.roll(streak, 3, axis=1) * 0.5)
            mask = mask * sparse * streak
        _composite(pixels, y0, x0, mask, color)
        return

    # ── Texture: random coarse texture, moderate coverage ────────────────────
    if bt == BrushType.TEXTURE:
        y0, x0, mask = _circular_mask(x, y, pixels, radius, 0.65, opacity * 0.80)
        if mask is not None:
            noise  = _varied_noise(mask.shape, seed)
            noise2 = _varied_noise((mask.shape[0] // 2 + 1, mask.shape[1] // 2 + 1), seed + 3)
            # Resize coarse noise to same shape
            coarse = np.kron(noise2[:mask.shape[0]//2+1, :mask.shape[1]//2+1],
                             np.ones((2, 2)))[:mask.shape[0], :mask.shape[1]]
            combined = (noise * 0.5 + coarse[:mask.shape[0], :mask.shape[1]] * 0.5)
            mask = mask * (combined > 0.35).astype(np.float32)
        _composite(pixels, y0, x0, mask, color)
        return

    # ── Scatter: random dots spread around cursor ─────────────────────────────
    if bt == BrushType.SCATTER:
        rng   = np.random.RandomState(seed & 0xFFFFFFFF)
        count = max(3, size // 4)
        h_px, w_px = pixels.shape[:2]
        for _ in range(count):
            ox = rng.uniform(-radius * 1.2, radius * 1.2)
            oy = rng.uniform(-radius * 1.2, radius * 1.2)
            dot_r = max(1.0, radius * rng.uniform(0.12, 0.30))
            y0, x0, mask = _circular_mask(x + ox, y + oy, pixels, dot_r, 0.9, opacity)
            _composite(pixels, y0, x0, mask, color)
        return

    # ── Pattern: stamp a checkerboard/crosshatch pattern ─────────────────────
    if bt == BrushType.PATTERN:
        y0, x0, mask = _circular_mask(x, y, pixels, radius, 0.9, opacity)
        if mask is not None:
            cell = max(2, size // 5)
            ys_i = np.arange(mask.shape[0])
            xs_i = np.arange(mask.shape[1])
            yy, xx = np.meshgrid(ys_i, xs_i, indexing='ij')
            checker = ((yy // cell + xx // cell) % 2).astype(np.float32)
            mask = mask * checker
        _composite(pixels, y0, x0, mask, color)
        return

    # ── Fallback: soft round ──────────────────────────────────────────────────
    y0, x0, mask = _circular_mask(x, y, pixels, radius, max(0.0, hardness * 0.5), opacity)
    _composite(pixels, y0, x0, mask, color)


# ─── Stroke interpolation ────────────────────────────────────────────────────

def paint_brush_stroke(pixels, x, y, color, size, hardness, opacity,
                       brush_type=None, prev_x=None, prev_y=None, stroke_seed=0):
    if brush_type is None:
        brush_type = BrushType.SOFT_ROUND
    paint_brush_dab(pixels, x, y, color, size, hardness, opacity,
                    brush_type, prev_x, prev_y, stroke_seed)


def paint_line(pixels, p0, p1, color, size, hardness, opacity,
               brush_type=None, stroke_seed=0):
    if brush_type is None:
        brush_type = BrushType.SOFT_ROUND
    x0, y0 = p0
    x1, y1 = p1
    dist  = math.hypot(x1 - x0, y1 - y0)
    # Step size: grain brushes need denser stepping for visible texture
    step  = max(0.5, size * 0.18)
    steps = max(1, int(dist / step))
    for i in range(steps + 1):
        t  = i / steps
        xi = x0 + t * (x1 - x0)
        yi = y0 + t * (y1 - y0)
        paint_brush_dab(pixels, xi, yi, color, size, hardness, opacity,
                        brush_type,
                        x0 + max(0, i-1)/steps*(x1-x0),
                        y0 + max(0, i-1)/steps*(y1-y0),
                        stroke_seed + i)


def erase_brush_stroke(pixels, x, y, size, hardness, opacity):
    radius = max(1.0, size / 2.0)
    y0, x0, mask = _circular_mask(x, y, pixels, radius, hardness, opacity)
    _erase(pixels, y0, x0, mask)


# ─── Flood fill ──────────────────────────────────────────────────────────────

def flood_fill(pixels, x, y, fill_color, tolerance=32):
    h, w = pixels.shape[:2]
    if not (0 <= x < w and 0 <= y < h):
        return
    seed_color = pixels[y, x].copy()
    target = np.array([fill_color.r, fill_color.g, fill_color.b, fill_color.a], dtype=np.uint8)
    if np.array_equal(seed_color, target):
        return
    diff     = pixels.astype(np.int32) - seed_color.astype(np.int32)
    dist     = np.sqrt((diff ** 2).sum(axis=2))
    fillable = dist <= tolerance
    visited  = np.zeros((h, w), dtype=bool)
    queue    = [(x, y)]
    visited[y, x] = True
    while queue:
        cx, cy = queue.pop()
        pixels[cy, cx] = target
        for nx, ny in ((cx+1,cy),(cx-1,cy),(cx,cy+1),(cx,cy-1)):
            if 0 <= nx < w and 0 <= ny < h and not visited[ny, nx] and fillable[ny, nx]:
                visited[ny, nx] = True
                queue.append((nx, ny))


# ─── Shape tools ─────────────────────────────────────────────────────────────

def draw_rectangle(pixels, x0, y0, x1, y1, color, filled=False, line_width=2):
    img = Image.fromarray(pixels, "RGBA"); draw = ImageDraw.Draw(img, "RGBA")
    rect = [min(x0,x1), min(y0,y1), max(x0,x1), max(y0,y1)]
    if filled: draw.rectangle(rect, fill=color.to_tuple())
    else:       draw.rectangle(rect, outline=color.to_tuple(), width=max(1,line_width))
    pixels[:] = np.array(img)

def draw_ellipse(pixels, x0, y0, x1, y1, color, filled=False, line_width=2):
    img = Image.fromarray(pixels, "RGBA"); draw = ImageDraw.Draw(img, "RGBA")
    rect = [min(x0,x1), min(y0,y1), max(x0,x1), max(y0,y1)]
    if filled: draw.ellipse(rect, fill=color.to_tuple())
    else:       draw.ellipse(rect, outline=color.to_tuple(), width=max(1,line_width))
    pixels[:] = np.array(img)

def draw_line_shape(pixels, x0, y0, x1, y1, color, line_width=2):
    img = Image.fromarray(pixels, "RGBA"); draw = ImageDraw.Draw(img, "RGBA")
    draw.line([x0, y0, x1, y1], fill=color.to_tuple(), width=max(1,line_width))
    pixels[:] = np.array(img)


# ─── Font resolution ─────────────────────────────────────────────────────────

_FONT_CACHE: dict = {}

_FONT_FILENAMES = {
    'arial':           ['arial.ttf', 'Arial.ttf'],
    'times new roman': ['times.ttf', 'timesnewroman.ttf', 'Times New Roman.ttf'],
    'courier new':     ['cour.ttf',  'CourierNew.ttf', 'Courier New.ttf'],
    'georgia':         ['georgia.ttf', 'Georgia.ttf'],
    'verdana':         ['verdana.ttf', 'Verdana.ttf'],
    'impact':          ['impact.ttf', 'Impact.ttf'],
    'comic sans ms':   ['comic.ttf',  'ComicSans.ttf'],
    'tahoma':          ['tahoma.ttf', 'Tahoma.ttf'],
    'trebuchet ms':    ['trebuc.ttf', 'Trebuchet MS.ttf'],
    'segoe ui':        ['segoeui.ttf','SegoeUI.ttf'],
    'calibri':         ['calibri.ttf','Calibri.ttf'],
}

def _font_search_dirs() -> list:
    import sys, os
    dirs = []
    if sys.platform == 'win32':
        win = os.environ.get('WINDIR', 'C:\\Windows')
        dirs.append(os.path.join(win, 'Fonts'))
        local = os.environ.get('LOCALAPPDATA', '')
        if local:
            dirs.append(os.path.join(local, 'Microsoft', 'Windows', 'Fonts'))
    elif sys.platform == 'darwin':
        dirs += ['/System/Library/Fonts', '/Library/Fonts',
                 os.path.expanduser('~/Library/Fonts')]
    else:
        dirs += ['/usr/share/fonts', '/usr/local/share/fonts',
                 os.path.expanduser('~/.fonts'), os.path.expanduser('~/.local/share/fonts')]
    return dirs

def _resolve_font_path(name: str) -> str | None:
    """Return the .ttf file path for a font name, or None if not found."""
    key = name.lower().strip()
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    
    candidates = _FONT_FILENAMES.get(key, [name + '.ttf', name.replace(' ', '') + '.ttf'])
    
    import os
    for d in _font_search_dirs():
        if not os.path.isdir(d):
            continue
        for cand in candidates:
            p = os.path.join(d, cand)
            if os.path.isfile(p):
                _FONT_CACHE[key] = p
                return p
        # Also try case-insensitive walk of the font dir
        try:
            for fn in os.listdir(d):
                if fn.lower() in [c.lower() for c in candidates]:
                    p = os.path.join(d, fn)
                    _FONT_CACHE[key] = p
                    return p
        except OSError:
            pass
    
    _FONT_CACHE[key] = None  # cache the miss
    return None

def _load_font(font_name: str, font_size: int):
    """Load a PIL font, always respecting font_size even if the named font is missing."""
    size = max(6, font_size)
    path = _resolve_font_path(font_name)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    # Try by name directly (works if PIL can find it on the system)
    try:
        return ImageFont.truetype(font_name, size)
    except Exception:
        pass
    # Final fallback: Pillow built-in scalable font (Pillow 10+)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


# ─── Text tool ───────────────────────────────────────────────────────────────

def draw_text(pixels, x, y, text, color, font_name="Arial", font_size=24):
    img = Image.fromarray(pixels, "RGBA"); draw = ImageDraw.Draw(img, "RGBA")
    font = _load_font(font_name, font_size)
    draw.text((x, y), text, fill=color.to_tuple(), font=font)
    pixels[:] = np.array(img)

def measure_text(text, font_name="Arial", font_size=24):
    """Return (width, height) of text in pixels."""
    font  = _load_font(font_name, font_size)
    dummy = Image.new("RGBA", (1, 1))
    draw  = ImageDraw.Draw(dummy)
    bb    = draw.textbbox((0, 0), text, font=font)
    return max(1, bb[2] - bb[0]), max(1, bb[3] - bb[1])


# ─── Eyedropper ──────────────────────────────────────────────────────────────

def pick_color(pixels, x, y):
    h, w = pixels.shape[:2]
    if not (0 <= x < w and 0 <= y < h):
        return None
    r, g, b, a = pixels[y, x]
    return Color(int(r), int(g), int(b), int(a))


# ─── Transform helpers ───────────────────────────────────────────────────────

def resize_layer_pixels(pixels, new_w, new_h):
    return np.array(Image.fromarray(pixels,"RGBA").resize((new_w,new_h),Image.LANCZOS),dtype=np.uint8)

def rotate_layer_pixels(pixels, angle, expand=False):
    return np.array(Image.fromarray(pixels,"RGBA").rotate(angle,expand=expand,resample=Image.BICUBIC),dtype=np.uint8)

def crop_layer_pixels(pixels, x0, y0, x1, y1):
    return np.array(Image.fromarray(pixels,"RGBA").crop((x0,y0,x1,y1)),dtype=np.uint8)
