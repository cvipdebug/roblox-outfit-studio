"""
core/models.py - Core data models for the Outfit Studio.

Defines Layer, Canvas, Project, and related data structures
used throughout the application.
"""

from __future__ import annotations

import uuid
import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Any
import numpy as np
from PIL import Image


class BlendMode(Enum):
    """Supported layer blending modes."""
    NORMAL = "normal"
    MULTIPLY = "multiply"
    SCREEN = "screen"
    OVERLAY = "overlay"
    SOFT_LIGHT = "soft_light"
    HARD_LIGHT = "hard_light"
    DIFFERENCE = "difference"
    EXCLUSION = "exclusion"
    ADD = "add"
    SUBTRACT = "subtract"


class ToolType(Enum):
    """Available painting / editing tools."""
    BRUSH = "brush"
    ERASER = "eraser"
    FILL = "fill"
    EYEDROPPER = "eyedropper"
    RECTANGLE = "rectangle"
    ELLIPSE = "ellipse"
    LINE = "line"
    TEXT = "text"
    TRANSFORM = "transform"
    SELECT = "select"



class BrushType(Enum):
    """All available brush types."""
    HARD_ROUND       = "hard_round"
    SOFT_ROUND       = "soft_round"
    AIRBRUSH         = "airbrush"
    SMUDGE           = "smudge"
    BLEND            = "blend"
    CHALK            = "chalk"
    CHARCOAL         = "charcoal"
    PENCIL           = "pencil"
    INK              = "ink"
    CALLIGRAPHY      = "calligraphy"
    FLAT             = "flat"
    TEXTURE          = "texture"
    SCATTER          = "scatter"
    WATERCOLOR       = "watercolor"
    OIL              = "oil"
    DRY_BRUSH        = "dry_brush"
    MARKER           = "marker"
    ERASER_SOFT      = "eraser_soft"
    ERASER_HARD      = "eraser_hard"
    PATTERN          = "pattern"

@dataclass
class Color:
    """RGBA color with helpers."""
    r: int = 0
    g: int = 0
    b: int = 0
    a: int = 255

    def to_tuple(self) -> tuple[int, int, int, int]:
        return (self.r, self.g, self.b, self.a)

    def to_hex(self) -> str:
        return f"#{self.r:02X}{self.g:02X}{self.b:02X}"

    @classmethod
    def from_hex(cls, hex_str: str, alpha: int = 255) -> "Color":
        hex_str = hex_str.lstrip("#")
        r = int(hex_str[0:2], 16)
        g = int(hex_str[2:4], 16)
        b = int(hex_str[4:6], 16)
        return cls(r, g, b, alpha)

    @classmethod
    def from_tuple(cls, t: tuple) -> "Color":
        if len(t) == 3:
            return cls(t[0], t[1], t[2])
        return cls(t[0], t[1], t[2], t[3])


# ── Layer Transform ───────────────────────────────────────────────────────────

@dataclass
class LayerTransform:
    """
    Non-destructive transform stored per-layer.
    All values are in canvas-pixel space / degrees.
    The original layer.pixels are NEVER modified until apply() is called.
    """
    x: float = 0.0          # translation X (canvas pixels)
    y: float = 0.0          # translation Y (canvas pixels)
    scale_x: float = 1.0    # horizontal scale factor
    scale_y: float = 1.0    # vertical scale factor
    rotation: float = 0.0   # degrees, counter-clockwise
    flip_h: bool = False
    flip_v: bool = False

    def is_identity(self) -> bool:
        return (self.x == 0 and self.y == 0
                and self.scale_x == 1.0 and self.scale_y == 1.0
                and self.rotation == 0.0
                and not self.flip_h and not self.flip_v)

    def copy(self) -> "LayerTransform":
        from dataclasses import replace
        return replace(self)

    def apply_to_pil(self, img: "Image.Image", canvas_w: int, canvas_h: int) -> "Image.Image":
        """
        Render the transformed image onto a canvas_w x canvas_h transparent canvas.
        The transform pivot is the centre of the original image.
        """
        from PIL import Image as PILImage
        import math

        result = PILImage.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        src = img.convert("RGBA")

        # Apply flips to source
        if self.flip_h:
            src = src.transpose(PILImage.FLIP_LEFT_RIGHT)
        if self.flip_v:
            src = src.transpose(PILImage.FLIP_TOP_BOTTOM)

        # Scale
        new_w = max(1, int(src.width  * abs(self.scale_x)))
        new_h = max(1, int(src.height * abs(self.scale_y)))
        if new_w != src.width or new_h != src.height:
            src = src.resize((new_w, new_h), PILImage.LANCZOS)

        # Rotate (expand so corners don't clip)
        if self.rotation != 0.0:
            src = src.rotate(-self.rotation, expand=True,
                             resample=PILImage.BICUBIC)

        # Paste centred on (translate_x + canvas_centre_x, ...)
        paste_x = int(canvas_w / 2 - src.width  / 2 + self.x)
        paste_y = int(canvas_h / 2 - src.height / 2 + self.y)
        result.paste(src, (paste_x, paste_y), src)
        return result

@dataclass
class Layer:
    """
    A single layer in the 2D clothing editor.

    Each layer stores its pixel data as a numpy RGBA array plus
    metadata such as name, opacity, blend mode, and visibility.
    """
    name: str
    width: int
    height: int
    layer_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    visible: bool = True
    opacity: float = 1.0          # 0.0 – 1.0
    blend_mode: BlendMode = BlendMode.NORMAL
    locked: bool = False
    pixels: Optional[np.ndarray] = field(default=None, repr=False)
    transform: "LayerTransform" = field(default_factory=LayerTransform)
    # Source pixels (original before any transform) - set when image is imported
    source_pixels: Optional[np.ndarray] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.pixels is None:
            # Transparent RGBA array
            self.pixels = np.zeros((self.height, self.width, 4), dtype=np.uint8)

    def clone(self) -> "Layer":
        """Return a deep copy of this layer."""
        new = Layer(
            name=self.name + " copy",
            width=self.width,
            height=self.height,
            layer_id=str(uuid.uuid4())[:8],
            visible=self.visible,
            opacity=self.opacity,
            blend_mode=self.blend_mode,
            locked=self.locked,
            pixels=self.pixels.copy(),
            transform=self.transform.copy(),
            source_pixels=self.source_pixels.copy() if self.source_pixels is not None else None,
        )
        return new

    def to_pil(self) -> Image.Image:
        """Convert pixel data to a PIL RGBA Image."""
        return Image.fromarray(self.pixels, mode="RGBA")

    def apply_transform(self) -> None:
        """
        Bake the current transform into pixels permanently.
        After this, transform resets to identity and source_pixels is cleared.
        """
        if self.source_pixels is not None and not self.transform.is_identity():
            raw = Image.fromarray(self.source_pixels, "RGBA")
            baked = self.transform.apply_to_pil(raw, self.width, self.height)
            import numpy as np
            self.pixels = np.array(baked, dtype=np.uint8)
        self.transform = LayerTransform()
        self.source_pixels = None

    def set_source(self, img: Image.Image) -> None:
        """Store original image as source and initialise transform."""
        import numpy as np
        img = img.convert("RGBA")
        self.source_pixels = np.array(img, dtype=np.uint8)
        # Reset pixels to transparent canvas (transform drives rendering)
        self.pixels = np.zeros((self.height, self.width, 4), dtype=np.uint8)
        self.transform = LayerTransform()

    def from_pil(self, img: Image.Image) -> None:
        """Load pixel data from a PIL Image (converted to RGBA)."""
        img = img.convert("RGBA").resize((self.width, self.height), Image.LANCZOS)
        self.pixels = np.array(img, dtype=np.uint8)

    def clear(self) -> None:
        """Fill the layer with transparent pixels."""
        self.pixels[:] = 0

    def fill(self, color: Color) -> None:
        """Fill the layer with a solid color."""
        self.pixels[:, :] = [color.r, color.g, color.b, color.a]


@dataclass
class ToolSettings:
    """Current tool configuration shared across the editor."""
    tool: ToolType = ToolType.BRUSH
    primary_color: Color = field(default_factory=lambda: Color(0, 0, 0, 255))
    secondary_color: Color = field(default_factory=lambda: Color(255, 255, 255, 255))
    brush_size: int = 10
    brush_hardness: float = 0.8    # 0.0 soft – 1.0 hard
    brush_opacity: float = 1.0
    fill_tolerance: int = 32
    font_name: str = "Arial"
    font_size: int = 24
    symmetry_axis: object = None   # SymmetryAxis enum value, None = off
    fill_selection_only: bool = False
    recent_colors: list = field(default_factory=list)   # up to 16 Color objects
    palette_colors: list = field(default_factory=lambda: [
        Color(0,0,0,255), Color(255,255,255,255),
        Color(255,0,0,255), Color(0,255,0,255), Color(0,0,255,255),
        Color(255,255,0,255), Color(255,128,0,255), Color(128,0,255,255),
        Color(255,0,128,255), Color(0,255,255,255), Color(128,64,0,255),
        Color(64,64,64,255), Color(128,128,128,255), Color(192,192,192,255),
        Color(0,128,0,255), Color(0,0,128,255),
    ])

    def __post_init__(self):
        from core.models import SymmetryAxis as _SA
        if self.symmetry_axis is None:
            self.symmetry_axis = _SA.NONE
    snap_to_grid: bool = False
    grid_size: int = 16
    brush_type: "BrushType" = field(default_factory=lambda: BrushType.SOFT_ROUND)
    shape_line_width: int = 2
    text_content: str = "Text"


@dataclass
class CanvasState:
    """
    Complete canvas state including all layers.

    This is the primary model that the editor manipulates.
    Serialised copies are stored in the undo/redo stack.
    """
    width: int = 585
    height: int = 559
    layers: List[Layer] = field(default_factory=list)
    active_layer_index: int = 0

    @property
    def active_layer(self) -> Optional[Layer]:
        if 0 <= self.active_layer_index < len(self.layers):
            return self.layers[self.active_layer_index]
        return None

    def add_layer(self, name: Optional[str] = None) -> Layer:
        name = name or f"Layer {len(self.layers) + 1}"
        layer = Layer(name=name, width=self.width, height=self.height)
        self.layers.append(layer)
        self.active_layer_index = len(self.layers) - 1
        return layer

    def remove_layer(self, index: int) -> None:
        if len(self.layers) <= 1:
            return
        self.layers.pop(index)
        self.active_layer_index = max(0, min(self.active_layer_index, len(self.layers) - 1))

    def move_layer(self, from_index: int, to_index: int) -> None:
        if from_index == to_index:
            return
        layer = self.layers.pop(from_index)
        self.layers.insert(to_index, layer)

    def flatten(self) -> Image.Image:
        """Composite all visible layers into a single PIL Image."""
        result = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        for layer in self.layers:
            if not layer.visible:
                continue
            # Always use source_pixels when present (even identity transform)
            if layer.source_pixels is not None:
                raw_img = Image.fromarray(layer.source_pixels, "RGBA")
                layer_img = layer.transform.apply_to_pil(raw_img, self.width, self.height)
            else:
                layer_img = layer.to_pil()
            if layer.opacity < 1.0:
                r, g, b, a = layer_img.split()
                a = a.point(lambda x: int(x * layer.opacity))
                layer_img = Image.merge("RGBA", (r, g, b, a))
            result = _composite_blend(result, layer_img, layer.blend_mode)
        return result

    def snapshot(self) -> "CanvasState":
        """Deep-copy the canvas for undo/redo."""
        new_state = CanvasState(
            width=self.width,
            height=self.height,
            active_layer_index=self.active_layer_index,
        )
        new_state.layers = [
            Layer(
                name=l.name,
                width=l.width,
                height=l.height,
                layer_id=l.layer_id,
                visible=l.visible,
                opacity=l.opacity,
                blend_mode=l.blend_mode,
                locked=l.locked,
                pixels=l.pixels.copy(),
                transform=l.transform.copy(),
                source_pixels=l.source_pixels.copy() if l.source_pixels is not None else None,
            )
            for l in self.layers
        ]
        return new_state


def _composite_blend(base: Image.Image, top: Image.Image, mode: BlendMode) -> Image.Image:
    """Apply a blend mode between two RGBA PIL images using proper alpha compositing."""
    if mode == BlendMode.NORMAL:
        return Image.alpha_composite(base, top)

    b = np.array(base, dtype=np.float32) / 255.0   # base  RGBA
    t = np.array(top,  dtype=np.float32) / 255.0   # top   RGBA

    br, bg, bb, ba = b[...,0], b[...,1], b[...,2], b[...,3]
    tr, tg, tb, ta = t[...,0], t[...,1], t[...,2], t[...,3]

    bc = b[..., :3]   # base RGB
    tc = t[..., :3]   # top  RGB

    # Blend the RGB channels
    if mode == BlendMode.MULTIPLY:
        rgb = bc * tc
    elif mode == BlendMode.SCREEN:
        rgb = 1.0 - (1.0 - bc) * (1.0 - tc)
    elif mode == BlendMode.OVERLAY:
        rgb = np.where(bc < 0.5,
                       2.0 * bc * tc,
                       1.0 - 2.0 * (1.0 - bc) * (1.0 - tc))
    elif mode == BlendMode.SOFT_LIGHT:
        rgb = np.where(tc < 0.5,
                       bc - (1.0 - 2.0*tc) * bc * (1.0 - bc),
                       bc + (2.0*tc - 1.0) * (np.sqrt(np.clip(bc, 0, 1)) - bc))
    elif mode == BlendMode.HARD_LIGHT:
        rgb = np.where(tc < 0.5,
                       2.0 * bc * tc,
                       1.0 - 2.0 * (1.0 - bc) * (1.0 - tc))
    elif mode == BlendMode.DIFFERENCE:
        rgb = np.abs(bc - tc)
    elif mode == BlendMode.EXCLUSION:
        rgb = bc + tc - 2.0 * bc * tc
    elif mode == BlendMode.ADD:
        rgb = np.clip(bc + tc, 0.0, 1.0)
    elif mode == BlendMode.SUBTRACT:
        rgb = np.clip(bc - tc, 0.0, 1.0)
    else:
        return Image.alpha_composite(base, top)

    # Porter-Duff "source over" alpha compositing with blended RGB
    ta3 = ta[..., np.newaxis]
    ba3 = ba[..., np.newaxis]
    out_a = ta3 + ba3 * (1.0 - ta3)
    safe  = np.where(out_a > 0, out_a, 1.0)
    out_rgb = (rgb * ta3 + bc * ba3 * (1.0 - ta3)) / safe
    out = np.clip(np.concatenate([out_rgb, out_a], axis=2) * 255, 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


@dataclass
class ProjectFile:
    """
    Serialisable representation of an entire editor project.

    Can be saved to / loaded from disk as a compressed archive.
    """
    name: str = "Untitled Project"
    canvas_width: int = 585
    canvas_height: int = 559
    template_type: str = "shirt"   # "shirt" | "pants" | "custom"
    layers_data: List[dict] = field(default_factory=list)
    tool_settings: dict = field(default_factory=dict)
    version: str = "1.0.0"


# ── Roblox template dimensions ──────────────────────────────────────────────

ROBLOX_SHIRT_SIZE = (585, 559)
ROBLOX_PANTS_SIZE = (585, 559)
ROBLOX_FACE_SIZE = (256, 256)

TEMPLATE_SIZES = {
    "shirt": ROBLOX_SHIRT_SIZE,
    "pants": ROBLOX_PANTS_SIZE,
    "face": ROBLOX_FACE_SIZE,
    "custom": (512, 512),
}


# ── Symmetry axis ────────────────────────────────────────────────────────────

class SymmetryAxis(Enum):
    NONE       = "none"
    HORIZONTAL = "horizontal"   # mirror left ↔ right
    VERTICAL   = "vertical"     # mirror top  ↔ bottom
    BOTH       = "both"
