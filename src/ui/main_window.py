"""
ui/main_window.py - Main application window.

Assembles the entire application:
  - Menu bar (File, Edit, View, Layer, Help)
  - Main toolbar (tools)
  - Left dock:  tool options
  - Centre:     2D canvas editor  |  3D avatar viewer  (splitter)
  - Right dock: layer panel
  - Right dock: viewer controls
  - Status bar
"""

from __future__ import annotations

import os
import io
from typing import Optional
import numpy as np
from PIL import Image as PILImage
from core.resources import resource_path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QDockWidget,
    QToolBar, QStatusBar, QFileDialog, QMessageBox,
    QInputDialog, QApplication, QLabel,
)
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSlot
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QColor

from core.models import CanvasState, ToolSettings, ToolType, Color, TEMPLATE_SIZES
from core.project_io import save_project, load_project, export_texture, export_template_png
from editor.canvas_widget import CanvasWidget
from viewer.gl_widget import AvatarViewerWidget
from ui.layer_panel import LayerPanel
from ui.tool_options import ToolOptionsPanel
from ui.viewer_controls import ViewerControlsPanel
from ui.theme_manager import ThemeManager, ThemeEditorDialog


# Tool button definitions: (name, symbol, tooltip, shortcut, tool_type)
TOOLS = [
    ("brush",      "✏",  "Brush (B)",         "B",  ToolType.BRUSH),
    ("eraser",     "⌫",  "Eraser (E)",         "E",  ToolType.ERASER),
    ("fill",       "🪣", "Fill / Bucket (G)",  "G",  ToolType.FILL),
    ("eyedrop",    "💧", "Eyedropper (I)",     "I",  ToolType.EYEDROPPER),
    ("rect",       "▭",  "Rectangle (R)",      "R",  ToolType.RECTANGLE),
    ("ellipse",    "⬭",  "Ellipse (C)",        "C",  ToolType.ELLIPSE),
    ("line",       "╱",  "Line (L)",           "L",  ToolType.LINE),
    ("text",       "T",  "Text (T)",           "",   ToolType.TEXT),
    ("transform",  "⇲",  "Transform (V)",      "V",  ToolType.TRANSFORM),
]


class MainWindow(QMainWindow):
    """Primary application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Roblox Outfit Studio")
        self.setMinimumSize(1200, 750)
        self.resize(1500, 900)

        # Application state
        self._canvas = CanvasState(width=585, height=559)
        self._canvas.add_layer("Background")
        self._tools = ToolSettings()
        self._project_path: Optional[str] = None
        self._dirty: bool = False
        self._template_type: str = "shirt"

        # 3D texture sync throttle
        self._sync_timer = QTimer(self)
        self._sync_timer.setSingleShot(True)
        self._sync_timer.setInterval(150)   # ms after last canvas change
        self._sync_timer.timeout.connect(self._push_texture_to_3d)

        # Theme system
        self._theme = ThemeManager()
        self._theme.load_config()

        self._build_ui()
        self._build_menus()
        self._build_toolbar()
        self._connect_signals()

        # Apply theme
        self._theme.apply_to(QApplication.instance())
        self._apply_viewer_bg()

        # Load shirt template as default canvas on startup (no dirty-check needed)
        self._load_default_template()

        # Initial 3D push
        self._sync_timer.start()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """Build central widget layout with canvas + 3D viewer splitter."""
        # Canvas widget (2D editor)
        self._canvas_widget = CanvasWidget(self._canvas, self._tools)
        self._canvas_widget.zoom_fit()

        # 3D viewer widget
        self._viewer_widget = AvatarViewerWidget()

        # Horizontal splitter: 2D left | 3D right
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.addWidget(self._canvas_widget)
        self._splitter.addWidget(self._viewer_widget)
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 2)
        self._splitter.setSizes([800, 500])

        self.setCentralWidget(self._splitter)

        # ── Left dock: Tool Options ────────────────────────────────────
        self._tool_options = ToolOptionsPanel(self._tools)
        tool_dock = QDockWidget("Tool Options", self)
        tool_dock.setWidget(self._tool_options)
        tool_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        tool_dock.setMinimumWidth(200)
        tool_dock.setMaximumWidth(260)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, tool_dock)

        # ── Right dock: Layers ─────────────────────────────────────────
        self._layer_panel = LayerPanel(self._canvas)
        layer_dock = QDockWidget("Layers", self)
        layer_dock.setWidget(self._layer_panel)
        layer_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        layer_dock.setMinimumWidth(200)
        layer_dock.setMaximumWidth(280)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, layer_dock)

        # ── Right dock: Viewer Controls ────────────────────────────────
        self._viewer_controls = ViewerControlsPanel()
        viewer_dock = QDockWidget("3D Controls", self)
        viewer_dock.setWidget(self._viewer_controls)
        viewer_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        viewer_dock.setMinimumWidth(200)
        viewer_dock.setMaximumWidth(280)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, viewer_dock)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_label = QLabel("Ready")
        self._status_bar.addWidget(self._status_label)

        # Coord label on right side
        self._coord_label = QLabel("")
        self._status_bar.addPermanentWidget(self._coord_label)

    def _build_toolbar(self) -> None:
        """Build the main painting tools toolbar."""
        self._tool_toolbar = QToolBar("Tools")
        self._tool_toolbar.setIconSize(QSize(24, 24))
        self._tool_toolbar.setMovable(False)
        self._tool_toolbar.setObjectName("tools_toolbar")
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._tool_toolbar)

        self._tool_actions: dict[ToolType, QAction] = {}

        for name, symbol, tooltip, shortcut, tool_type in TOOLS:
            action = QAction(symbol, self)
            action.setToolTip(tooltip)
            action.setCheckable(True)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(lambda checked, t=tool_type: self._select_tool(t))
            self._tool_toolbar.addAction(action)
            self._tool_actions[tool_type] = action

        # Separator
        self._tool_toolbar.addSeparator()

        # Zoom controls
        zoom_in_act  = QAction("🔍+", self)
        zoom_in_act.setToolTip("Zoom In (=)")
        zoom_in_act.setShortcut(QKeySequence("="))
        zoom_in_act.triggered.connect(self._canvas_widget.zoom_in)
        self._tool_toolbar.addAction(zoom_in_act)

        zoom_out_act = QAction("🔍-", self)
        zoom_out_act.setToolTip("Zoom Out (-)")
        zoom_out_act.setShortcut(QKeySequence("-"))
        zoom_out_act.triggered.connect(self._canvas_widget.zoom_out)
        self._tool_toolbar.addAction(zoom_out_act)

        zoom_fit_act = QAction("⊡", self)
        zoom_fit_act.setToolTip("Fit to Window (0)")
        zoom_fit_act.setShortcut(QKeySequence("0"))
        zoom_fit_act.triggered.connect(self._canvas_widget.zoom_fit)
        self._tool_toolbar.addAction(zoom_fit_act)

        zoom_100_act = QAction("1:1", self)
        zoom_100_act.setToolTip("100% Zoom (1)")
        zoom_100_act.setShortcut(QKeySequence("1"))
        zoom_100_act.triggered.connect(self._canvas_widget.zoom_100)
        self._tool_toolbar.addAction(zoom_100_act)

        # Select default tool
        self._select_tool(ToolType.BRUSH)

    def _build_menus(self) -> None:
        """Build the application menu bar."""
        menubar = self.menuBar()

        # ── File ──────────────────────────────────────────────────────────
        file_menu = menubar.addMenu("File")

        new_act = QAction("New Project", self)
        new_act.setShortcut(QKeySequence.StandardKey.New)
        new_act.triggered.connect(self._on_new)
        file_menu.addAction(new_act)

        open_act = QAction("Open Project…", self)
        open_act.setShortcut(QKeySequence.StandardKey.Open)
        open_act.triggered.connect(self._on_open)
        file_menu.addAction(open_act)

        save_act = QAction("Save Project", self)
        save_act.setShortcut(QKeySequence.StandardKey.Save)
        save_act.triggered.connect(self._on_save)
        file_menu.addAction(save_act)

        saveas_act = QAction("Save Project As…", self)
        saveas_act.setShortcut(QKeySequence.StandardKey.SaveAs)
        saveas_act.triggered.connect(self._on_save_as)
        file_menu.addAction(saveas_act)

        file_menu.addSeparator()

        import_act = QAction("Import Image as Layer…", self)
        import_act.setShortcut(QKeySequence("Ctrl+I"))
        import_act.triggered.connect(self._on_import_image)
        file_menu.addAction(import_act)

        file_menu.addSeparator()

        export_act = QAction("Export Texture PNG…", self)
        export_act.setShortcut(QKeySequence("Ctrl+E"))
        export_act.triggered.connect(self._on_export_texture)
        file_menu.addAction(export_act)

        template_act = QAction("Export Blank Template…", self)
        template_act.triggered.connect(self._on_export_template)
        file_menu.addAction(template_act)

        file_menu.addSeparator()

        exit_act = QAction("Exit", self)
        exit_act.setShortcut(QKeySequence.StandardKey.Quit)
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        # ── Edit ──────────────────────────────────────────────────────────
        edit_menu = menubar.addMenu("Edit")

        undo_act = QAction("Undo", self)
        undo_act.setShortcut(QKeySequence.StandardKey.Undo)
        undo_act.triggered.connect(self._canvas_widget.undo)
        edit_menu.addAction(undo_act)

        redo_act = QAction("Redo", self)
        redo_act.setShortcut(QKeySequence.StandardKey.Redo)
        redo_act.triggered.connect(self._canvas_widget.redo)
        edit_menu.addAction(redo_act)

        edit_menu.addSeparator()

        clear_act = QAction("Clear Active Layer", self)
        clear_act.setShortcut(QKeySequence("Delete"))
        clear_act.triggered.connect(self._on_clear_layer)
        edit_menu.addAction(clear_act)

        apply_tx_act = QAction("Apply Transform", self)
        apply_tx_act.setShortcut("Ctrl+Shift+A")
        apply_tx_act.triggered.connect(self._canvas_widget.apply_transform)
        edit_menu.addAction(apply_tx_act)

        reset_tx_act = QAction("Reset Transform", self)
        reset_tx_act.triggered.connect(self._canvas_widget.reset_transform)
        edit_menu.addAction(reset_tx_act)

        edit_menu.addSeparator()
        flatten_act = QAction("Flatten All Layers", self)
        flatten_act.triggered.connect(self._on_flatten_all)
        edit_menu.addAction(flatten_act)

        # ── Canvas ────────────────────────────────────────────────────────
        canvas_menu = menubar.addMenu("Canvas")

        shirt_act = QAction("New Shirt Template (585×559)", self)
        shirt_act.triggered.connect(lambda: self._new_from_template("shirt"))
        canvas_menu.addAction(shirt_act)

        pants_act = QAction("New Pants Template (585×559)", self)
        pants_act.triggered.connect(lambda: self._new_from_template("pants"))
        canvas_menu.addAction(pants_act)

        custom_act = QAction("New Custom Size…", self)
        custom_act.triggered.connect(self._on_new_custom)
        canvas_menu.addAction(custom_act)

        # ── Layer ─────────────────────────────────────────────────────────
        layer_menu = menubar.addMenu("Layer")

        add_act = QAction("Add Layer", self)
        add_act.setShortcut(QKeySequence("Ctrl+Shift+N"))
        add_act.triggered.connect(self._layer_panel._on_add_layer)
        layer_menu.addAction(add_act)

        del_act = QAction("Delete Layer", self)
        del_act.triggered.connect(self._layer_panel._on_delete_layer)
        layer_menu.addAction(del_act)

        dup_act = QAction("Duplicate Layer", self)
        dup_act.setShortcut(QKeySequence("Ctrl+J"))
        dup_act.triggered.connect(self._layer_panel._on_duplicate_layer)
        layer_menu.addAction(dup_act)

        merge_act = QAction("Merge Down", self)
        merge_act.setShortcut(QKeySequence("Ctrl+Shift+E"))
        merge_act.triggered.connect(self._layer_panel._on_merge_down)
        layer_menu.addAction(merge_act)

        # ── Theme ────────────────────────────────────────────────────────
        theme_menu = menubar.addMenu("Theme")
        theme_edit_act = QAction("Theme Editor…", self)
        theme_edit_act.triggered.connect(self._open_theme_editor)
        theme_menu.addAction(theme_edit_act)
        theme_menu.addSeparator()
        for _tname in ["Dark (Default)", "Light", "Neon", "Ocean"]:
            _act = QAction(_tname, self)
            _act.triggered.connect(lambda _, n=_tname: self._apply_builtin_theme(n))
            theme_menu.addAction(_act)

        # ── Help ─────────────────────────────────────────────────────────
        help_menu = menubar.addMenu("Help")
        about_act = QAction("About Roblox Outfit Studio", self)
        about_act.triggered.connect(self._on_about)
        help_menu.addAction(about_act)

        shortcuts_act = QAction("Keyboard Shortcuts", self)
        shortcuts_act.triggered.connect(self._on_shortcuts)
        help_menu.addAction(shortcuts_act)

    def _connect_signals(self) -> None:
        """Wire all cross-widget signals."""
        # Canvas → 3D sync
        self._canvas_widget.canvas_changed.connect(self._on_canvas_changed)
        self._canvas_widget.canvas_replaced.connect(self._on_canvas_replaced)
        self._canvas_widget.color_picked.connect(self._on_color_picked)
        self._canvas_widget.status_message.connect(self._coord_label.setText)

        # Layer panel → canvas refresh
        self._layer_panel.layers_changed.connect(self._on_layers_changed)
        self._layer_panel.opacity_changed.connect(self._on_layers_changed_simple)
        self._layer_panel.layer_selected.connect(self._on_layer_selected)

        # Tool options → canvas
        self._tool_options.tool_settings_changed.connect(self._canvas_widget.update)

        # Transform tool: tool_options ↔ canvas_widget bidirectional sync
        self._tool_options.transform_flip_h.connect(self._canvas_widget.flip_transform_h)
        self._tool_options.transform_flip_v.connect(self._canvas_widget.flip_transform_v)
        self._tool_options.transform_reset.connect(self._canvas_widget.reset_transform)
        self._tool_options.transform_apply.connect(self._canvas_widget.apply_transform)
        self._tool_options.transform_changed.connect(self._canvas_widget.set_transform_from_panel)
        self._canvas_widget.transform_display_update.connect(
            self._tool_options.update_transform_display)

        # Viewer controls → 3D widget
        self._viewer_controls.camera_preset.connect(self._viewer_widget.set_camera_preset)
        self._viewer_controls.ambient_changed.connect(self._viewer_widget.set_ambient)
        self._viewer_controls.diffuse_changed.connect(self._viewer_widget.set_diffuse)
        self._viewer_controls.auto_rotate.connect(self._viewer_widget.set_auto_rotate)
        self._viewer_controls.grid_toggled.connect(self._viewer_widget.set_show_grid)
        self._viewer_controls.template_changed.connect(self._on_template_changed)

    # ── Tool selection ────────────────────────────────────────────────────────

    def _select_tool(self, tool: ToolType) -> None:
        for t, action in self._tool_actions.items():
            action.setChecked(t == tool)
        self._tools.tool = tool
        self._tool_options.refresh_for_tool(tool)
        self._status_label.setText(f"Tool: {tool.value.replace('_', ' ').title()}")

    # ── Slots ─────────────────────────────────────────────────────────────────

    @pyqtSlot(object)
    @pyqtSlot(object)
    def _on_canvas_replaced(self, new_state) -> None:
        """Called after undo/redo – resync all refs to the new canvas state."""
        self._canvas = new_state
        self._layer_panel._canvas = new_state
        self._layer_panel.refresh()
        # 3D push is triggered by canvas_changed which fires right after this

    def _on_canvas_changed(self, _flat_image) -> None:
        """Canvas was painted – schedule a throttled 3D texture push."""
        self._dirty = True
        self._sync_timer.start()
        self._update_title()

    @pyqtSlot()
    def _on_layers_changed(self) -> None:
        self._canvas_widget.canvas = self._canvas
        self._canvas_widget._invalidate_cache()
        self._canvas_widget.update()
        self._dirty = True
        self._sync_timer.start()
        self._update_title()

    @pyqtSlot()
    def _on_layers_changed_simple(self, *_) -> None:
        self._on_layers_changed()

    @pyqtSlot(int)
    def _on_layer_selected(self, idx: int) -> None:
        self._canvas.active_layer_index = idx
        self._canvas_widget.canvas = self._canvas

    @pyqtSlot(object)
    def _on_color_picked(self, color: Color) -> None:
        self._tool_options.set_primary_color(color)

    @pyqtSlot(str)
    def _on_template_changed(self, tmpl: str) -> None:
        self._template_type = tmpl
        self._push_texture_to_3d()

    def _load_default_template(self) -> None:
        """Load the shirt template image as the startup canvas."""
        _tmpl = resource_path("assets", "templates", "shirt_template_default.png")
        if os.path.exists(_tmpl):
            try:
                img = PILImage.open(_tmpl).convert("RGBA")
                guide = self._canvas.layers[0]  # use the Background layer
                guide.name = "Template Guide"
                guide.opacity = 0.55
                guide.pixels = np.array(img.resize((585, 559), PILImage.LANCZOS), dtype=np.uint8)
                # Add a blank paint layer on top
                self._canvas.add_layer("Layer 1")
                self._canvas.active_layer_index = 1
                self._canvas_widget.canvas = self._canvas
                self._canvas_widget._invalidate_cache()
                self._layer_panel._canvas = self._canvas
                self._layer_panel.refresh()
            except Exception:
                pass

    def _apply_viewer_bg(self) -> None:
        r, g, b = self._theme.get_viewer_bg()
        self._viewer_widget.set_bg_color(r, g, b)

    def _open_theme_editor(self) -> None:
        dlg = ThemeEditorDialog(self._theme, self)
        dlg.theme_changed.connect(self._on_theme_changed)
        dlg.exec()
        self._theme.save_config()

    def _apply_builtin_theme(self, name: str) -> None:
        self._theme.set_builtin(name)
        self._theme.apply_to(QApplication.instance())
        self._theme.save_config()
        self._apply_viewer_bg()

    def _on_theme_changed(self) -> None:
        self._theme.apply_to(QApplication.instance())
        self._apply_viewer_bg()

    def _push_texture_to_3d(self) -> None:
        """Flatten canvas and upload to 3D viewer as appropriate texture."""
        # Always use canvas_widget's canvas - it's authoritative (undo may have replaced it)
        flat = self._canvas_widget.canvas.flatten()
        if self._template_type == "shirt":
            self._viewer_widget.update_shirt_texture(flat)
        else:
            self._viewer_widget.update_pants_texture(flat)

    # ── File operations ──────────────────────────────────────────────────────

    def _on_new(self) -> None:
        if self._dirty and not self._confirm_discard():
            return
        self._canvas = CanvasState(width=585, height=559)
        self._canvas.add_layer("Background")
        self._canvas_widget.canvas = self._canvas
        self._canvas_widget._invalidate_cache()
        self._layer_panel._canvas = self._canvas
        self._layer_panel.refresh()
        self._project_path = None
        self._dirty = False
        self._update_title()
        self._push_texture_to_3d()

    def _on_open(self) -> None:
        if self._dirty and not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "", "Outfit Project (*.outfitproj)"
        )
        if not path:
            return
        try:
            canvas = load_project(path)
            self._canvas = canvas
            self._canvas_widget.canvas = canvas
            self._canvas_widget._invalidate_cache()
            self._layer_panel._canvas = canvas
            self._layer_panel.refresh()
            self._project_path = path
            self._dirty = False
            self._update_title()
            self._push_texture_to_3d()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open project:\n{e}")

    def _on_save(self) -> None:
        if self._project_path:
            self._do_save(self._project_path)
        else:
            self._on_save_as()

    def _on_save_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project", "untitled.outfitproj", "Outfit Project (*.outfitproj)"
        )
        if path:
            self._do_save(path)

    def _do_save(self, path: str) -> None:
        try:
            save_project(self._canvas, path)
            self._project_path = path
            self._dirty = False
            self._update_title()
            self._status_label.setText(f"Saved: {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save:\n{e}")

    def _on_import_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.tga)"
        )
        if path:
            self._canvas_widget.import_image_file(path)
            self._layer_panel.refresh()

    def _on_export_texture(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Texture", "texture.png", "PNG Image (*.png)"
        )
        if path:
            try:
                export_texture(self._canvas, path, self._template_type)
                self._status_label.setText(f"Exported: {os.path.basename(path)}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Export failed:\n{e}")

    def _on_export_template(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Template Guide", "template.png", "PNG Image (*.png)"
        )
        if path:
            export_template_png(self._template_type, path)
            self._status_label.setText("Template exported")

    def _on_clear_layer(self) -> None:
        layer = self._canvas.active_layer
        if layer and not layer.locked:
            self._canvas_widget._push_history()
            layer.clear()
            self._canvas_widget._invalidate_cache()
            self._push_texture_to_3d()

    def _on_flatten_all(self) -> None:
        flat = self._canvas.flatten()
        self._canvas.layers.clear()
        bg = self._canvas.add_layer("Flattened")
        bg.pixels = np.array(flat, dtype=np.uint8)
        self._canvas_widget.canvas = self._canvas
        self._canvas_widget._invalidate_cache()
        self._layer_panel.refresh()
        self._push_texture_to_3d()

    def _new_from_template(self, template_type: str) -> None:
        if self._dirty and not self._confirm_discard():
            return
        w, h = TEMPLATE_SIZES[template_type]
        self._canvas = CanvasState(width=w, height=h)
        # Layer 1: blank painting canvas (bottom)
        self._canvas.add_layer("Background")
        # Layer 2: the real Roblox template image as a reference guide (top, semi-transparent)
        guide = self._canvas.add_layer("Template Guide")

        # Try to load the real template image bundled with the app
        _assets = resource_path("assets", "templates")
        _asset_map = {
            "shirt": os.path.join(_assets, "shirt_template_default.png"),
            "pants": os.path.join(_assets, "pants_template_default.png"),
        }
        _tmpl_path = os.path.normpath(_asset_map.get(template_type, ""))
        if os.path.exists(_tmpl_path):
            try:
                img = PILImage.open(_tmpl_path).convert("RGBA").resize((w, h), PILImage.LANCZOS)
                guide.pixels = np.array(img, dtype=np.uint8)
                guide.opacity = 0.55   # semi-transparent so user can paint underneath
            except Exception:
                pass  # silently fall back to blank guide
        else:
            # Fallback: generate a simple guide overlay
            import tempfile, os
            tmp_fd, buf_path = tempfile.mkstemp(suffix=".png")
            os.close(tmp_fd)
            try:
                export_template_png(template_type, buf_path)
                img = PILImage.open(buf_path).convert("RGBA")
                guide.pixels = np.array(img, dtype=np.uint8)
            finally:
                try: os.unlink(buf_path)
                except OSError: pass

        self._template_type = template_type
        self._canvas_widget.canvas = self._canvas
        self._canvas_widget._invalidate_cache()
        self._layer_panel._canvas = self._canvas
        self._layer_panel.refresh()
        self._project_path = None
        self._dirty = False
        self._update_title()
        self._push_texture_to_3d()

    def _on_new_custom(self) -> None:
        w, ok = QInputDialog.getInt(self, "Canvas Width", "Width (px):", 512, 64, 4096)
        if not ok:
            return
        h, ok2 = QInputDialog.getInt(self, "Canvas Height", "Height (px):", 512, 64, 4096)
        if not ok2:
            return
        if self._dirty and not self._confirm_discard():
            return
        self._canvas = CanvasState(width=w, height=h)
        self._canvas.add_layer("Background")
        self._canvas_widget.canvas = self._canvas
        self._canvas_widget._invalidate_cache()
        self._layer_panel._canvas = self._canvas
        self._layer_panel.refresh()
        self._project_path = None
        self._dirty = False
        self._update_title()

    # ── Help dialogs ─────────────────────────────────────────────────────────

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            "About Roblox Outfit Studio",
            "<h2>Roblox Outfit Studio</h2>"
            "<p>Version 1.0.0</p>"
            "<p>A Python rewrite and extension of the SlothX Outfit Viewer.<br>"
            "Combines a full 2D clothing editor with a real-time 3D avatar preview.</p>"
            "<p><b>Features:</b><ul>"
            "<li>Layer-based 2D clothing editor</li>"
            "<li>Brush, fill, shape, text painting tools</li>"
            "<li>PyOpenGL 3D avatar viewer</li>"
            "<li>Real-time 2D→3D texture sync</li>"
            "<li>Roblox shirt & pants template support</li>"
            "<li>Project save/load (.outfitproj)</li>"
            "</ul></p>"
        )

    def _on_shortcuts(self) -> None:
        QMessageBox.information(
            self,
            "Keyboard Shortcuts",
            "<b>Tools</b><br>"
            "B – Brush &nbsp;&nbsp; E – Eraser<br>"
            "G – Fill &nbsp;&nbsp;&nbsp; I – Eyedropper<br>"
            "R – Rectangle &nbsp; C – Ellipse<br>"
            "L – Line &nbsp;&nbsp;&nbsp; V – Transform<br><br>"
            "<b>File</b><br>"
            "Ctrl+N – New &nbsp; Ctrl+O – Open<br>"
            "Ctrl+S – Save &nbsp; Ctrl+E – Export &nbsp; Ctrl+Shift+E – Merge Down<br>"
            "Ctrl+I – Import<br><br>"
            "<b>Edit</b><br>"
            "Ctrl+Z – Undo &nbsp; Ctrl+Y – Redo<br>"
            "Delete – Clear Layer<br><br>"
            "<b>View</b><br>"
            "= / - &nbsp; Zoom In / Out<br>"
            "0 – Fit to Window &nbsp; 1 – 100%<br><br>"
            "<b>Canvas (Middle Mouse)</b><br>"
            "Pan the canvas view",
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _confirm_discard(self) -> bool:
        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved changes. Discard them?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
        )
        return reply == QMessageBox.StandardButton.Discard

    def _update_title(self) -> None:
        name = os.path.basename(self._project_path) if self._project_path else "Untitled"
        dirty = " •" if self._dirty else ""
        self.setWindowTitle(f"Roblox Outfit Studio — {name}{dirty}")

    def closeEvent(self, event) -> None:
        if self._dirty:
            reply = QMessageBox.question(
                self,
                "Quit",
                "Save changes before exiting?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Save:
                self._on_save()
                event.accept()
            elif reply == QMessageBox.StandardButton.Discard:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
