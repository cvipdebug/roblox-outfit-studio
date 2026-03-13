"""
core/advanced_template.py
UV mapping for the "Dripzels Resources" advanced Roblox shirt template.

PIXEL-VERIFIED from Advanced_Template__Labeled_.png, roblox_shirt.png,
and roblox_shirt_template.png (all 585x559).

Advanced template grid structure
---------------------------------
Column BORDER lines (bright ~155 px):
  x = 31, 97, 163, 229, 359, 425, 555

Shade-change boundaries (no bright line, definitive cell split):
  x = 295  (splits wide col3a/3b: r_leg_front / l_leg_front in rows 2-3)
  x = 491  (splits wide col5a/5b: l_leg_back / r_leg_back in row 2)

Row BORDER lines:
  y = 6, 72, 202, 332, 398

Cell content x-ranges (content BETWEEN the border lines):
  col0 : x=32-96    (64px)  arms_sides only (row 1)
  col1 : x=98-162   (64px)
  col2 : x=164-228  (64px)
  col3a: x=230-294  (64px)  combined as 128px wide block in rows 0-1
  col3b: x=295-358  (63px)  split into own cell in rows 2-3
  col4 : x=360-424  (64px)
  col5a: x=426-490  (64px)  combined as 128px wide block in rows 0-1
  col5b: x=491-554  (63px)  split into own cell in row 2

Cell content y-ranges:
  row0: y=8-72    (64px)   tops & bottoms
  row1: y=74-202  (128px)  main body faces
  row2: y=204-332 (128px)  arms_bottom (64px tall only) + leg faces
  row3: y=334-398 (64px)   leg bottoms

Cell assignments:
  row0: col1=arms_top, col3a+3b=torso_top(128px), col5a+5b=torso_bottom(128px)
  row1: col0=arms_sides, col1=arms_front_back, col2=torso_side_r,
        col3a+3b=torso_front(128px), col4=torso_side_l, col5a+5b=torso_back(128px)
  row2: col1=arms_bottom(y=204-268 only), col2=r_leg_sides,
        col3a=r_leg_front, col3b=l_leg_front,
        col4=l_leg_sides, col5a=l_leg_back, col5b=r_leg_back
  row3: col3a=r_leg_bottom, col3b=l_leg_bottom

Official Roblox 585x559 template face layout (verified from roblox_shirt.png):
  Torso: top(231,8)-(359,72), front(231,74)-(359,202), right(165,74)-(229,202),
         left(361,74)-(425,202), back(427,74)-(555,202), bottom(231,204)-(359,268)
  Right arm col order L->R: L(outer,x19-82) | B(back,x85-148) | R(inner,x151-214) | F(front,x217-280)
    U above F: y=289-352   D below F: y=485-549
  Left arm col order L->R: F(front,x308-371) | L(inner,x374-437) | B(back,x440-503) | R(outer,x506-569)
    U above F: y=289-352   D below F: y=485-549
  Pants legs use IDENTICAL pixel coordinates to shirt arms.
"""
from __future__ import annotations
from PIL import Image
import numpy as np


# ---------------------------------------------------------------------------
# Advanced template source regions (pixel-verified)
# ---------------------------------------------------------------------------
ADV_REGIONS = {
    # Row 0 (y=8-72, 64px tall)
    "arms_top":         ( 98,   8, 162,  72),   # col1
    "torso_top":        (230,   8, 358,  72),   # col3a+3b, 128px wide
    "torso_bottom":     (426,   8, 554,  72),   # col5a+5b, 128px wide

    # Row 1 (y=74-202, 128px tall)
    "arms_sides":       ( 32,  74,  96, 202),   # col0
    "arms_front_back":  ( 98,  74, 162, 202),   # col1
    "torso_side_r":     (164,  74, 228, 202),   # col2
    "torso_front":      (230,  74, 358, 202),   # col3a+3b, 128px wide
    "torso_side_l":     (360,  74, 424, 202),   # col4
    "torso_back":       (426,  74, 554, 202),   # col5a+5b, 128px wide

    # Row 2 (y=204-332, 128px tall; arms_bottom is only 64px tall)
    "arms_bottom":      ( 98, 204, 162, 268),   # col1, y=204-268 (64px)
    "r_leg_sides":      (164, 204, 228, 332),   # col2
    "r_leg_front":      (230, 204, 294, 332),   # col3a
    "l_leg_front":      (295, 204, 358, 332),   # col3b
    "l_leg_sides":      (360, 204, 424, 332),   # col4
    "l_leg_back":       (426, 204, 490, 332),   # col5a
    "r_leg_back":       (491, 204, 554, 332),   # col5b

    # Row 3 (y=334-398, 64px tall)
    "r_leg_bottom":     (230, 334, 294, 398),   # col3a
    "l_leg_bottom":     (295, 334, 358, 398),   # col3b
}


# ---------------------------------------------------------------------------
# Official Roblox 585x559 destination regions (pixel-verified)
# ---------------------------------------------------------------------------
ROB_REGIONS = {
    # Torso (used by both shirt and pants)
    "torso_top":      (231,   8, 359,  72),
    "torso_front":    (231,  74, 359, 202),
    "torso_side_r":   (165,  74, 229, 202),   # character RIGHT (-x)
    "torso_side_l":   (361,  74, 425, 202),   # character LEFT  (+x)
    "torso_back":     (427,  74, 555, 202),
    "torso_bottom":   (231, 204, 359, 268),

    # Right arm (shirt only)
    "r_arm_top":      (217, 289, 280, 352),
    "r_arm_front":    (217, 355, 280, 483),   # F faces viewer (+z)
    "r_arm_back":     ( 85, 355, 148, 483),   # B faces away   (-z)
    "r_arm_right":    ( 19, 355,  82, 483),   # L col = outer  (-x)
    "r_arm_left":     (151, 355, 214, 483),   # R col = inner toward torso (+x)
    "r_arm_bottom":   (217, 485, 280, 549),

    # Left arm (shirt only)
    "l_arm_top":      (308, 289, 371, 352),
    "l_arm_front":    (308, 355, 371, 483),   # F faces viewer (+z)
    "l_arm_back":     (440, 355, 503, 483),   # B faces away   (-z)
    "l_arm_right":    (374, 355, 437, 483),   # L col = inner toward torso (-x)
    "l_arm_left":     (506, 355, 569, 483),   # R col = outer  (+x)
    "l_arm_bottom":   (308, 485, 371, 549),

    # Right leg (pants only - same pixel layout as right arm)
    "r_leg_top":      (217, 289, 280, 352),
    "r_leg_front":    (217, 355, 280, 483),
    "r_leg_back":     ( 85, 355, 148, 483),
    "r_leg_right":    ( 19, 355,  82, 483),   # outer (-x)
    "r_leg_left":     (151, 355, 214, 483),   # inner (+x)
    "r_leg_bottom":   (217, 485, 280, 549),

    # Left leg (pants only - same pixel layout as left arm)
    "l_leg_top":      (308, 289, 371, 352),
    "l_leg_front":    (308, 355, 371, 483),
    "l_leg_back":     (440, 355, 503, 483),
    "l_leg_right":    (374, 355, 437, 483),   # inner (-x)
    "l_leg_left":     (506, 355, 569, 483),   # outer (+x)
    "l_leg_bottom":   (308, 485, 371, 549),
}


# ---------------------------------------------------------------------------
# Remap tables
# CRITICAL: Roblox shirt arms and pants legs share IDENTICAL pixel coordinates
# (both at y=289-549). Shirt and pants outputs must use separate remap tables.
# ---------------------------------------------------------------------------

REMAP_SHIRT = [
    # Torso
    ("torso_top",        "torso_top"),
    ("torso_front",      "torso_front"),
    ("torso_side_r",     "torso_side_r"),
    ("torso_side_l",     "torso_side_l"),
    ("torso_back",       "torso_back"),
    ("torso_bottom",     "torso_bottom"),
    # Arms - single source fills same face on both arms
    ("arms_top",         "r_arm_top"),
    ("arms_top",         "l_arm_top"),
    ("arms_front_back",  "r_arm_front"),
    ("arms_front_back",  "r_arm_back"),
    ("arms_front_back",  "l_arm_front"),
    ("arms_front_back",  "l_arm_back"),
    ("arms_sides",       "r_arm_right"),
    ("arms_sides",       "r_arm_left"),
    ("arms_sides",       "l_arm_right"),
    ("arms_sides",       "l_arm_left"),
    ("arms_bottom",      "r_arm_bottom"),
    ("arms_bottom",      "l_arm_bottom"),
]

REMAP_PANTS = [
    # Torso
    ("torso_top",        "torso_top"),
    ("torso_front",      "torso_front"),
    ("torso_side_r",     "torso_side_r"),
    ("torso_side_l",     "torso_side_l"),
    ("torso_back",       "torso_back"),
    ("torso_bottom",     "torso_bottom"),
    # Right leg
    ("r_leg_front",      "r_leg_front"),
    ("r_leg_back",       "r_leg_back"),
    ("r_leg_sides",      "r_leg_right"),
    ("r_leg_sides",      "r_leg_left"),
    ("r_leg_bottom",     "r_leg_bottom"),
    # Left leg
    ("l_leg_front",      "l_leg_front"),
    ("l_leg_back",       "l_leg_back"),
    ("l_leg_sides",      "l_leg_right"),
    ("l_leg_sides",      "l_leg_left"),
    ("l_leg_bottom",     "l_leg_bottom"),
]

# Backwards-compat alias
REMAP = REMAP_SHIRT


# ---------------------------------------------------------------------------
# Conversion functions
# ---------------------------------------------------------------------------

def _paste_region(src: Image.Image, dst: Image.Image,
                  sx1: int, sy1: int, sx2: int, sy2: int,
                  dx1: int, dy1: int, dx2: int, dy2: int) -> None:
    """Crop src rect, scale to destination size, alpha-paste onto dst."""
    sw, sh = sx2 - sx1, sy2 - sy1
    dw, dh = dx2 - dx1, dy2 - dy1
    if sw <= 0 or sh <= 0 or dw <= 0 or dh <= 0:
        return
    patch = src.crop((sx1, sy1, sx2, sy2))
    if patch.size != (dw, dh):
        patch = patch.resize((dw, dh), Image.LANCZOS)
    dst.paste(patch, (dx1, dy1), patch)


def advanced_to_roblox(adv_img: Image.Image,
                        tmpl_type: str = "shirt") -> Image.Image:
    """Convert advanced-template painting to official Roblox 585x559 UV layout.

    tmpl_type: "shirt" (default) or "pants"
    """
    remap = REMAP_SHIRT if tmpl_type == "shirt" else REMAP_PANTS
    if adv_img.size != (585, 559):
        adv_img = adv_img.resize((585, 559), Image.LANCZOS)
    out = Image.new("RGBA", (585, 559), (0, 0, 0, 0))
    for adv_key, rob_key in remap:
        ar = ADV_REGIONS.get(adv_key)
        rr = ROB_REGIONS.get(rob_key)
        if ar and rr:
            _paste_region(adv_img, out, *ar, *rr)
    return out


def roblox_to_advanced(rob_img: Image.Image,
                        tmpl_type: str = "shirt") -> Image.Image:
    """Reverse: official Roblox UV layout -> advanced template space."""
    remap = REMAP_SHIRT if tmpl_type == "shirt" else REMAP_PANTS
    if rob_img.size != (585, 559):
        rob_img = rob_img.resize((585, 559), Image.LANCZOS)
    out = Image.new("RGBA", (585, 559), (0, 0, 0, 0))
    seen: set = set()
    for adv_key, rob_key in remap:
        if adv_key in seen:
            continue
        seen.add(adv_key)
        ar = ADV_REGIONS.get(adv_key)
        rr = ROB_REGIONS.get(rob_key)
        if ar and rr:
            _paste_region(rob_img, out, *rr, *ar)
    return out


# ---------------------------------------------------------------------------
# Region display metadata
# ---------------------------------------------------------------------------
REGION_META = {
    "arms_top":        {"label": "Arms\nTop",        "color": (255, 200,  50, 80)},
    "torso_top":       {"label": "Torso\nTop",        "color": ( 50, 200, 255, 80)},
    "torso_bottom":    {"label": "Torso\nBottom",     "color": ( 50, 200, 150, 80)},
    "arms_sides":      {"label": "Arms\nSides",       "color": (200, 100, 255, 80)},
    "arms_front_back": {"label": "Arms\nFront+Back",  "color": (255, 100, 200, 80)},
    "torso_side_r":    {"label": "Torso\nSide R",     "color": (100, 255, 100, 80)},
    "torso_front":     {"label": "Torso\nFront",      "color": ( 50, 150, 255, 80)},
    "torso_side_l":    {"label": "Torso\nSide L",     "color": (100, 200, 100, 80)},
    "torso_back":      {"label": "Torso\nBack",       "color": (255, 100,  50, 80)},
    "arms_bottom":     {"label": "Arms\nBottom",      "color": (180, 100, 255, 80)},
    "r_leg_sides":     {"label": "R Leg\nSides",      "color": (255,  50, 150, 80)},
    "r_leg_front":     {"label": "R Leg\nFront",      "color": ( 50, 220, 220, 80)},
    "l_leg_front":     {"label": "L Leg\nFront",      "color": ( 50, 180, 220, 80)},
    "l_leg_sides":     {"label": "L Leg\nSides",      "color": (100, 150, 255, 80)},
    "l_leg_back":      {"label": "L Leg\nBack",       "color": (255, 180, 100, 80)},
    "r_leg_back":      {"label": "R Leg\nBack",       "color": (200, 140,  80, 80)},
    "r_leg_bottom":    {"label": "R Leg\nBottom",     "color": (200, 200,  50, 80)},
    "l_leg_bottom":    {"label": "L Leg\nBottom",     "color": (200, 150,  50, 80)},
}


def draw_uv_overlay(canvas_w: int, canvas_h: int,
                    mode: str = "advanced") -> Image.Image:
    """Return a transparent RGBA overlay with coloured fills + labels per region."""
    from PIL import ImageDraw, ImageFont
    overlay = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    sx = canvas_w / 585
    sy = canvas_h / 559

    if mode == "advanced":
        regions = ADV_REGIONS
    else:
        show_keys = [
            "torso_top", "torso_front", "torso_side_r", "torso_side_l",
            "torso_back", "torso_bottom",
            "r_arm_front", "l_arm_front", "r_leg_front", "l_leg_front",
            "r_leg_back",  "l_leg_back",
        ]
        regions = {k: ROB_REGIONS[k] for k in show_keys if k in ROB_REGIONS}

    try:
        font = ImageFont.load_default(size=10)
    except Exception:
        font = ImageFont.load_default()

    for key, (x1, y1, x2, y2) in regions.items():
        meta = REGION_META.get(key, {
            "label": key.replace("_", " ").title(),
            "color": (180, 180, 180, 80),
        })
        col = meta["color"]
        rx1, ry1 = int(x1 * sx), int(y1 * sy)
        rx2, ry2 = int(x2 * sx), int(y2 * sy)
        draw.rectangle([rx1, ry1, rx2, ry2], fill=col[:3] + (55,))
        draw.rectangle([rx1, ry1, rx2, ry2], outline=col[:3] + (200,), width=2)
        label = meta["label"]
        cx = (rx1 + rx2) // 2
        cy = (ry1 + ry2) // 2
        lines = label.split("\n")
        for i, line in enumerate(lines):
            bb = draw.textbbox((0, 0), line, font=font)
            tw, th = bb[2] - bb[0], bb[3] - bb[1]
            ty = cy - (len(lines) * (th + 1)) // 2 + i * (th + 1)
            draw.text((cx - tw // 2 + 1, ty + 1), line, fill=(0, 0, 0, 200),      font=font)
            draw.text((cx - tw // 2,     ty),     line, fill=(255, 255, 255, 230), font=font)

    return overlay
