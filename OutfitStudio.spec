# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\cvip\\Desktop\\python stuff\\Roblox shirt editor\\roblox_outfit_studio_py311_v19\\roblox_outfit_studio_311\\src\\main.py'],
    pathex=['C:\\Users\\cvip\\Desktop\\python stuff\\Roblox shirt editor\\roblox_outfit_studio_py311_v19\\roblox_outfit_studio_311\\src'],
    binaries=[],
    datas=[('C:\\Users\\cvip\\Desktop\\python stuff\\Roblox shirt editor\\roblox_outfit_studio_py311_v19\\roblox_outfit_studio_311\\assets\\templates\\pants_template.png', 'assets/templates'), ('C:\\Users\\cvip\\Desktop\\python stuff\\Roblox shirt editor\\roblox_outfit_studio_py311_v19\\roblox_outfit_studio_311\\assets\\templates\\pants_template_default.png', 'assets/templates'), ('C:\\Users\\cvip\\Desktop\\python stuff\\Roblox shirt editor\\roblox_outfit_studio_py311_v19\\roblox_outfit_studio_311\\assets\\templates\\sample_shirt.png', 'assets/templates'), ('C:\\Users\\cvip\\Desktop\\python stuff\\Roblox shirt editor\\roblox_outfit_studio_py311_v19\\roblox_outfit_studio_311\\assets\\templates\\shirt_template.png', 'assets/templates'), ('C:\\Users\\cvip\\Desktop\\python stuff\\Roblox shirt editor\\roblox_outfit_studio_py311_v19\\roblox_outfit_studio_311\\assets\\templates\\shirt_template_default.png', 'assets/templates'), ('C:\\Users\\cvip\\Desktop\\python stuff\\Roblox shirt editor\\roblox_outfit_studio_py311_v19\\roblox_outfit_studio_311\\assets\\icon.ico', 'assets'), ('C:\\Users\\cvip\\Desktop\\python stuff\\Roblox shirt editor\\roblox_outfit_studio_py311_v19\\roblox_outfit_studio_311\\assets\\icon.png', 'assets')],
    hiddenimports=['PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets', 'PyQt6.QtOpenGL', 'PyQt6.QtOpenGLWidgets', 'OpenGL', 'OpenGL.GL', 'OpenGL.GLU', 'OpenGL.GL.shaders', 'OpenGL.arrays', 'OpenGL.arrays.numpymodule', 'OpenGL.platform', 'OpenGL.platform.win32', 'PIL', 'PIL.Image', 'PIL.ImageDraw', 'PIL.ImageFont', 'PIL.ImageFilter', 'PIL._tkinter_finder', 'numpy', 'numpy.core', 'numpy.core._multiarray_umath', 'core', 'core.models', 'core.paint_engine', 'core.history', 'core.project_io', 'core.resources', 'editor', 'editor.canvas_widget', 'ui', 'ui.main_window', 'ui.layer_panel', 'ui.tool_options', 'ui.viewer_controls', 'ui.theme_manager', 'viewer', 'viewer.gl_widget'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='OutfitStudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:\\Users\\cvip\\Desktop\\python stuff\\Roblox shirt editor\\roblox_outfit_studio_py311_v19\\roblox_outfit_studio_311\\assets\\icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='OutfitStudio',
)
