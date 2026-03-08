"""
utils/generate_samples.py - Generate sample assets for development and testing.

Creates:
  - assets/templates/shirt_template.png
  - assets/templates/pants_template.png
  - assets/avatars/default_avatar_preview.png
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")


def generate_shirt_template(output_path: str) -> None:
    """Generate a Roblox shirt UV template (585×559)."""
    w, h = 585, 559
    img = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Region definitions: label → (x0, y0, x1, y1, colour)
    regions = [
        ("Torso Front",  102, 234, 204, 338, (180, 210, 255, 255)),
        ("Torso Back",   205, 234, 307, 338, (180, 230, 210, 255)),
        ("L. Arm",         0, 234, 101, 338, (255, 220, 180, 255)),
        ("R. Arm",       308, 234, 409, 338, (255, 200, 200, 255)),
        ("L. Sleeve",      0, 339,  98, 443, (220, 255, 220, 255)),
        ("R. Sleeve",    308, 339, 406, 443, (220, 220, 255, 255)),
        ("Head",         104,  0, 204, 100, (255, 240, 210, 255)),
        ("Hat",          205,   0, 305,  60, (240, 240, 240, 255)),
    ]

    try:
        font = ImageFont.truetype("Arial", 12)
        small_font = ImageFont.truetype("Arial", 10)
    except Exception:
        font = ImageFont.load_default()
        small_font = font

    # Light grey background
    draw.rectangle([0, 0, w - 1, h - 1], fill=(230, 230, 230, 255))

    for label, x0, y0, x1, y1, color in regions:
        draw.rectangle([x0, y0, x1, y1], fill=color)
        draw.rectangle([x0, y0, x1, y1], outline=(100, 100, 120, 255), width=1)
        # Centred label
        text_x = (x0 + x1) // 2 - 20
        text_y = (y0 + y1) // 2 - 8
        draw.text((text_x, text_y), label, fill=(50, 50, 80, 255), font=font)

    # Grid lines at 100px intervals
    for x in range(0, w, 100):
        draw.line([(x, 0), (x, h)], fill=(180, 180, 200, 120), width=1)
    for y in range(0, h, 100):
        draw.line([(0, y), (w, y)], fill=(180, 180, 200, 120), width=1)

    # Watermark
    draw.text((4, h - 18), "Roblox Shirt Template 585×559", fill=(150, 150, 170, 200), font=small_font)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, format="PNG")
    print(f"  Generated: {output_path}")


def generate_pants_template(output_path: str) -> None:
    """Generate a Roblox pants UV template (585×559)."""
    w, h = 585, 559
    img = Image.new("RGBA", (w, h), (230, 230, 230, 255))
    draw = ImageDraw.Draw(img)

    regions = [
        ("L. Leg Front",   0,   0, 196, 480, (200, 230, 255, 255)),
        ("R. Leg Front", 200,   0, 396, 480, (220, 255, 220, 255)),
        ("Waist",          0, 481, 196, 558, (255, 230, 200, 255)),
        ("L. Leg Back",  200, 481, 396, 558, (255, 220, 220, 255)),
    ]

    try:
        font = ImageFont.truetype("Arial", 13)
        small_font = ImageFont.truetype("Arial", 10)
    except Exception:
        font = ImageFont.load_default()
        small_font = font

    for label, x0, y0, x1, y1, color in regions:
        draw.rectangle([x0, y0, x1, y1], fill=color)
        draw.rectangle([x0, y0, x1, y1], outline=(100, 100, 120, 255), width=1)
        draw.text((x0 + 4, y0 + 4), label, fill=(50, 50, 80, 255), font=font)

    for x in range(0, w, 100):
        draw.line([(x, 0), (x, h)], fill=(180, 180, 200, 120), width=1)
    for y in range(0, h, 100):
        draw.line([(0, y), (w, y)], fill=(180, 180, 200, 120), width=1)

    draw.text((4, h - 18), "Roblox Pants Template 585×559", fill=(150, 150, 170, 200), font=small_font)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, format="PNG")
    print(f"  Generated: {output_path}")


def generate_sample_shirt(output_path: str) -> None:
    """Generate a colourful sample shirt texture for demonstration."""
    w, h = 585, 559
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Paint base colour on shirt regions
    regions = [
        (102, 234, 204, 338),   # Torso Front
        (205, 234, 307, 338),   # Torso Back
        (0,   234, 101, 338),   # Left Arm
        (308, 234, 409, 338),   # Right Arm
        (0,   339,  98, 443),   # Left Sleeve
        (308, 339, 406, 443),   # Right Sleeve
    ]
    base_color = (52, 120, 200, 255)
    stripe_color = (220, 240, 255, 255)

    for x0, y0, x1, y1 in regions:
        draw.rectangle([x0, y0, x1, y1], fill=base_color)
        # Horizontal stripes
        for sy in range(y0, y1, 12):
            draw.line([(x0, sy), (x1, sy)], fill=stripe_color, width=3)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, format="PNG")
    print(f"  Generated: {output_path}")


if __name__ == "__main__":
    print("Generating sample assets...")
    templates_dir = os.path.join(ASSETS_DIR, "templates")
    generate_shirt_template(os.path.join(templates_dir, "shirt_template.png"))
    generate_pants_template(os.path.join(templates_dir, "pants_template.png"))
    generate_sample_shirt(os.path.join(templates_dir, "sample_shirt.png"))
    print("Done.")
