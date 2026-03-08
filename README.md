# 🎨 Roblox Outfit Studio

A free, open-source **desktop clothing editor** for Roblox — paint shirts and pants in 2D with a full layer-based editor and see your design on a 3D R6 avatar in real time.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![PyQt6](https://img.shields.io/badge/UI-PyQt6-green?logo=qt&logoColor=white)
![OpenGL](https://img.shields.io/badge/3D-OpenGL-orange)
![License](https://img.shields.io/badge/License-MIT-lightgrey)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-informational)

---

## ✨ Features

### 🖌️ 2D Clothing Editor
- **Full layer system** — add, delete, duplicate, reorder, lock, hide, and set opacity per layer
- **Blend modes** — Normal, Multiply, Screen, Overlay, Add, Subtract, and more
- **Brush & Eraser** — adjustable size (1–500px), hardness, and opacity with smooth stroke interpolation
- **Non-destructive Transform tool** — move, scale, rotate, and flip imported images with on-canvas handles; nothing is baked until you choose to
- **Fill / Bucket** — configurable tolerance flood fill
- **Eyedropper** — pick any colour from any visible layer
- **Shape tools** — Rectangle, Ellipse, Line
- **Text tool** — system font picker with size control
- **Import images** — PNG, JPG, BMP, WebP as new layers; drag-and-drop supported
- **Undo / Redo** — 100-step history
- **Zoom** — 10% to 1600% with scroll-wheel, keyboard shortcuts, and fit-to-window
- **Snap to grid** — configurable grid size

### 🧍 Real-Time 3D Avatar Preview
- **R6 avatar** — accurate Roblox R6 body proportions (stud-correct dimensions)
- **Live texture sync** — 2D canvas changes appear on the 3D avatar automatically
- **Orbit camera** — left-drag to orbit, right-drag to pan, scroll to zoom
- **Camera presets** — Front, Back, Left, Right, Top, ¾ View
- **Lighting controls** — adjustable ambient and diffuse sliders
- **Ground grid** and **auto-rotate** toggle

### 🎨 Theme System
- 4 built-in themes: **Dark** (default), **Light**, **Neon**, **Ocean**
- Full theme editor with colour pickers for every UI element
- Import / export themes as JSON

### 💾 Project & Export
- Save/load projects as `.outfitproj` (layers + metadata, ZIP-based)
- Export final texture as a Roblox-ready **585×559 PNG**
- Export blank UV template guides
- New canvas from Shirt template, Pants template, or custom size

---

## 🚀 Quick Start

### Requirements
- Python **3.10** or newer
- Any system with OpenGL support (any modern GPU or integrated graphics)

### Run from source

```bash
# 1. Clone
git clone https://github.com/cvipdebug/roblox-outfit-studio.git
cd roblox-outfit-studio

# 2. Create a virtual environment (recommended)
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Launch
python src/main.py
```

### Dependencies

| Package | Purpose |
|---------|---------|
| `PyQt6` | GUI framework |
| `Pillow` | Image loading, blending, export |
| `numpy` | Fast pixel painting |
| `PyOpenGL` | 3D avatar renderer |
| `PyOpenGL_accelerate` | Optional C accelerators |

---

## 📦 Building a Standalone .exe (Windows)

No Python required on the user's machine.

```bash
pip install pyinstaller
python build_dist.py
```

Output goes into `dist/OutfitStudio/` — distribute the whole folder. Users run `OutfitStudio.exe`.

The build script automatically bundles all template PNGs, the app icon, and all required hidden imports for PyQt6 + PyOpenGL.

---

## ⌨️ Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `B` | Brush |
| `E` | Eraser |
| `G` | Fill / Bucket |
| `I` | Eyedropper |
| `R` | Rectangle |
| `C` | Ellipse |
| `L` | Line |
| `T` | Text |
| `V` | Transform |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` | Redo |
| `Ctrl+S` | Save project |
| `Ctrl+E` | Export texture PNG |
| `Ctrl+I` | Import image as layer |
| `Ctrl+Shift+N` | New layer |
| `=` / `-` | Zoom in / out |
| `0` | Fit to window |
| `1` | 100% zoom |
| `Delete` | Clear active layer |

---

## 📐 Roblox Template Reference

| Template | Size | Regions |
|----------|------|---------|
| Shirt | 585 × 559 px | Torso (front/back/sides/top/bottom), Left arm, Right arm |
| Pants | 585 × 559 px | Torso (waistband), Left leg, Right leg |

Exported PNGs match the official Roblox UV layout and can be uploaded directly to Roblox Studio or the Roblox website.

---

## 🗂️ Project Structure

```
roblox-outfit-studio/
├── src/
│   ├── main.py                  # Entry point
│   ├── core/
│   │   ├── models.py            # Layer, CanvasState, LayerTransform, Color
│   │   ├── history.py           # Undo/redo stack
│   │   ├── paint_engine.py      # All pixel painting operations
│   │   ├── project_io.py        # Save/load/export
│   │   └── resources.py         # Cross-platform asset path resolver
│   ├── editor/
│   │   └── canvas_widget.py     # 2D canvas + Transform tool handles
│   ├── viewer/
│   │   └── gl_widget.py         # PyOpenGL 3D R6 avatar renderer
│   └── ui/
│       ├── main_window.py       # Main application window
│       ├── layer_panel.py       # Layer management panel
│       ├── tool_options.py      # Tool options sidebar
│       ├── viewer_controls.py   # 3D viewer controls
│       └── theme_manager.py     # Theme system + editor dialog
├── assets/
│   ├── icon.ico                 # App icon (16–256px, all sizes)
│   ├── icon.png                 # App icon 256px PNG
│   └── templates/
│       ├── shirt_template_default.png
│       └── pants_template_default.png
├── tests/
├── requirements.txt
├── build_dist.py                # PyInstaller build script
└── README.md
```

---

## 🤝 Contributing

Pull requests are welcome! Some ideas for future improvements:

- R15 avatar support
- Load actual Roblox `.rbxm` avatar models
- Selection / lasso tool
- GLSL shader rendering for higher visual quality
- Roblox API integration (fetch avatar by username)
- Animation preview (idle, walk cycle)
- macOS `.app` build

---

## 📄 License

MIT License — see [`LICENSE`](LICENSE) for details.

---

## 🙏 Credits

3D avatar preview concept inspired by [SlothX Outfit Viewer](https://github.com/SlothXTheDev/slothxoutfitviewer).
