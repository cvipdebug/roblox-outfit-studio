"""
build_dist.py  -  Build Roblox Outfit Studio into a standalone Windows exe.

Usage (from the project root folder):
    python build_dist.py

Output: dist/OutfitStudio/OutfitStudio.exe   (and all supporting files)

Requirements: pip install pyinstaller
"""

import os
import sys
import subprocess
import shutil

ROOT   = os.path.dirname(os.path.abspath(__file__))
SRC    = os.path.join(ROOT, "src")
MAIN   = os.path.join(SRC,  "main.py")
ASSETS = os.path.join(ROOT, "assets")
DIST   = os.path.join(ROOT, "dist")
BUILD  = os.path.join(ROOT, "build")
NAME   = "OutfitStudio"

SEP = os.pathsep   # ";" on Windows, ":" on Linux/macOS


def run():
    print("=" * 60)
    print("  Roblox Outfit Studio  —  PyInstaller build")
    print("=" * 60)

    # ── 1. Make sure PyInstaller is installed ─────────────────────────────────
    try:
        import PyInstaller  # noqa: F401
        print("[OK] PyInstaller found")
    except ImportError:
        print("[..] Installing PyInstaller…")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # ── 2. Clean previous build artefacts ─────────────────────────────────────
    for d in (DIST, BUILD):
        if os.path.exists(d):
            shutil.rmtree(d)
            print(f"[..] Cleaned {d}")

    # ── 3. Collect --add-data entries ─────────────────────────────────────────
    #
    # Format:  "<source_path><SEP><dest_folder_inside_bundle>"
    #
    # Everything under assets/ goes into assets/ inside the exe bundle.
    # resource_path("assets","templates","foo.png") will find them at runtime
    # via sys._MEIPASS/assets/templates/foo.png.
    #
    add_data = []

    # All template PNGs
    tmpl_dir = os.path.join(ASSETS, "templates")
    if os.path.isdir(tmpl_dir):
        for fname in os.listdir(tmpl_dir):
            if fname.lower().endswith(".png"):
                src_file = os.path.join(tmpl_dir, fname)
                add_data += ["--add-data", f"{src_file}{SEP}assets/templates"]
        print(f"[OK] Found {len([f for f in os.listdir(tmpl_dir) if f.endswith('.png')])} template PNGs")
    else:
        print("[!!] WARNING: assets/templates/ not found — templates will be missing!")

    # Bundle the icon so resource_path() can find it at runtime too
    for icon_name in ("icon.ico", "icon.png"):
        icon_file = os.path.join(ASSETS, icon_name)
        if os.path.exists(icon_file):
            add_data += ["--add-data", f"{icon_file}{SEP}assets"]
            print(f"[OK] Bundling {icon_name}")

    # Any other asset subdirs (icons, fonts, etc.)
    for subdir in os.listdir(ASSETS):
        full = os.path.join(ASSETS, subdir)
        if os.path.isdir(full) and subdir != "templates":
            add_data += ["--add-data", f"{full}{SEP}assets/{subdir}"]

    # ── 4. Hidden imports ─────────────────────────────────────────────────────
    #
    # PyInstaller's static analyser misses dynamic imports. List them all here.
    #
    hidden = [
        # PyQt6
        "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets",
        "PyQt6.QtOpenGL", "PyQt6.QtOpenGLWidgets",
        # OpenGL
        "OpenGL", "OpenGL.GL", "OpenGL.GLU", "OpenGL.GL.shaders",
        "OpenGL.arrays", "OpenGL.arrays.numpymodule",
        "OpenGL.platform", "OpenGL.platform.win32",
        # PIL / Pillow
        "PIL", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont",
        "PIL.ImageFilter", "PIL._tkinter_finder",
        # Numpy
        "numpy", "numpy.core", "numpy.core._multiarray_umath",
        # App internal packages (PyInstaller may miss them)
        "core", "core.models", "core.paint_engine", "core.history",
        "core.project_io", "core.resources",
        "editor", "editor.canvas_widget",
        "ui", "ui.main_window", "ui.layer_panel",
        "ui.tool_options", "ui.viewer_controls",
        "ui.theme_manager",
        "viewer", "viewer.gl_widget",
    ]

    hidden_flags = []
    for h in hidden:
        hidden_flags += ["--hidden-import", h]

    # ── 5. Build the command ──────────────────────────────────────────────────
    # Icon path
    icon_path = os.path.join(ASSETS, "icon.ico")
    icon_flags = ["--icon", icon_path] if os.path.exists(icon_path) else []
    if icon_flags:
        print(f"[OK] Icon: {icon_path}")
    else:
        print("[!!] WARNING: assets/icon.ico not found — no icon will be set")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name",       NAME,
        "--onedir",             # folder bundle — faster startup than --onefile
        "--windowed",           # no console window
        "--clean",
        "--noconfirm",
        "--distpath",   DIST,
        "--workpath",   BUILD,
        "--paths",      SRC,    # so PyInstaller finds our packages
    ] + icon_flags + add_data + hidden_flags + [MAIN]

    # ── 6. Run ────────────────────────────────────────────────────────────────
    print(f"\n[..] Running PyInstaller…\n")
    result = subprocess.run(cmd)

    if result.returncode != 0:
        print("\n❌  Build FAILED. Read the output above for errors.")
        sys.exit(1)

    # ── 7. Verify key outputs exist ───────────────────────────────────────────
    exe_path = os.path.join(DIST, NAME, f"{NAME}.exe")
    if not os.path.exists(exe_path):
        # macOS / Linux
        exe_path = os.path.join(DIST, NAME, NAME)

    out_dir  = os.path.join(DIST, NAME)
    tmpl_out = os.path.join(out_dir, "assets", "templates")

    print("\n" + "=" * 60)
    print("  Build complete — verification")
    print("=" * 60)
    print(f"  Exe  : {exe_path}  {'✅' if os.path.exists(exe_path) else '❌ MISSING'}")
    print(f"  Tmpls: {tmpl_out}  {'✅' if os.path.isdir(tmpl_out) else '❌ MISSING'}")
    if os.path.isdir(tmpl_out):
        pngs = [f for f in os.listdir(tmpl_out) if f.endswith(".png")]
        for p in pngs:
            print(f"         • {p}")

    print(f"\n✅  Done!  Distribute the whole  dist/{NAME}/  folder.")
    print(f"   Users run:  {NAME}.exe\n")


if __name__ == "__main__":
    run()
