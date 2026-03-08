"""
core/resources.py - Runtime asset path resolution.

Works correctly in three contexts:
  1. Running from source:  returns path relative to project root
  2. PyInstaller --onedir: returns path inside the extracted _MEIPASS temp dir
  3. PyInstaller --onefile: same as (2)

Usage:
    from core.resources import resource_path
    img_path = resource_path("assets", "templates", "shirt_template_default.png")
"""
from __future__ import annotations
import os
import sys


def resource_path(*parts: str) -> str:
    """
    Return an absolute path to a bundled resource.

    In a frozen PyInstaller exe, assets live inside sys._MEIPASS.
    In development they live at <project_root>/<parts>.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # PyInstaller unpacks data files into sys._MEIPASS at runtime
        base = sys._MEIPASS
    else:
        # Running from source: go up from src/core/ to project root
        base = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
    return os.path.join(base, *parts)
