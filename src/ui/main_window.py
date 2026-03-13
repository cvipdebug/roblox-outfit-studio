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
    ("select",     "⬚",  "Select (S)",         "S",  ToolType.SELECT),
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
        self._advanced_mode: bool = False

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

        # Auto-save + crash recovery (after UI is ready)
        self._autosave_path   = ""
        self._autosave_timer  = None
        self._setup_autosave()

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
        viewer_dock.setMinimumWidth(240)
        viewer_dock.setMaximumWidth(340)
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

        adv_shirt_act = QAction("New Advanced Shirt Template…", self)
        adv_shirt_act.setToolTip("Use the high-res advanced UV layout for more detail")
        adv_shirt_act.triggered.connect(lambda: self._new_advanced_template("shirt"))
        file_menu.addAction(adv_shirt_act)

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

        roblox_export_act = QAction("Export for Roblox Upload…", self)
        roblox_export_act.setShortcut("Ctrl+Shift+E")
        roblox_export_act.triggered.connect(self._on_export_roblox)
        file_menu.addAction(roblox_export_act)
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

        sel_all_act = QAction("Select All", self)
        sel_all_act.setShortcut("Ctrl+A")
        sel_all_act.triggered.connect(self._canvas_widget.select_all)
        edit_menu.addAction(sel_all_act)

        desel_act = QAction("Deselect", self)
        desel_act.setShortcut("Ctrl+D")
        desel_act.triggered.connect(self._canvas_widget.clear_selection)
        edit_menu.addAction(desel_act)

        edit_menu.addSeparator()

        copy_act = QAction("Copy", self)
        copy_act.triggered.connect(self._canvas_widget.copy_selection)
        edit_menu.addAction(copy_act)

        cut_act = QAction("Cut", self)
        cut_act.triggered.connect(self._canvas_widget.cut_selection)
        edit_menu.addAction(cut_act)

        paste_act = QAction("Paste", self)
        paste_act.triggered.connect(self._canvas_widget.paste_selection)
        edit_menu.addAction(paste_act)

        del_act = QAction("Delete Selection", self)
        del_act.triggered.connect(self._canvas_widget.delete_selection)
        edit_menu.addAction(del_act)

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

        uv_act = QAction("Show UV Overlay", self)
        uv_act.setCheckable(True)
        uv_act.setShortcut("U")
        uv_act.triggered.connect(self._on_uv_overlay)
        canvas_menu.addAction(uv_act)
        self._uv_action = uv_act

        canvas_menu.addSeparator()

        export_adv_act = QAction("Export Advanced → Roblox Upload…", self)
        export_adv_act.setShortcut("Ctrl+Shift+R")
        export_adv_act.setToolTip("Convert advanced template layout to official Roblox format and save")
        export_adv_act.triggered.connect(self._on_export_advanced)
        canvas_menu.addAction(export_adv_act)

        canvas_menu.addSeparator()

        # Symmetry submenu
        sym_menu = canvas_menu.addMenu("Symmetry")
        for label, val in [("None", "none"), ("Horizontal ↔", "horizontal"),
                           ("Vertical ↕", "vertical"), ("Both ✛", "both")]:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setData(val)
            act.triggered.connect(lambda checked, v=val: self._on_symmetry(v))
            sym_menu.addAction(act)
        self._sym_menu = sym_menu

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
        self._tool_options.tool_settings_changed.connect(self._canvas_widget.sync_text_settings)
        self._canvas_widget.text_object_selected.connect(self._tool_options.set_text_font)
        self._canvas_widget.recent_colors_changed.connect(self._tool_options.refresh_recent_colors)

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
        self._viewer_controls.skin_color_changed.connect(self._viewer_widget.set_skin_color)

    def _setup_autosave(self):
        import tempfile
        self._autosave_path = os.path.join(
            tempfile.gettempdir(), "roblox_outfit_studio_recovery.outfitproj"
        )
        if os.path.exists(self._autosave_path):
            reply = QMessageBox.question(
                self, "Crash Recovery",
                "A recovery file was found from a previous session. Restore it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    self._load_project_file(self._autosave_path)
                    self._project_path = None
                    self._dirty = True
                    self._update_title()
                    self._status_label.setText("Session recovered from auto-save.")
                except Exception as e:
                    QMessageBox.warning(self, "Recovery Failed", str(e))
            try:
                os.remove(self._autosave_path)
            except Exception:
                pass

        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(120_000)
        self._autosave_timer.timeout.connect(self._do_autosave)
        self._autosave_timer.start()

    def _do_autosave(self):
        if not self._dirty or not self._autosave_path:
            return
        try:
            from core.project_io import save_project
            save_project(self._canvas, self._autosave_path)
            self._status_label.setText("Auto-saved.")
        except Exception:
            pass



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
        """Flatten canvas and upload to 3D viewer as appropriate texture.

        Advanced mode: ALL visible layers (including the guide) are flattened
        together and then converted from advanced-UV space to Roblox-UV space.
        The guide layer pixels only land in cells defined by ADV_REGIONS, so
        they map to the correct faces on the 3D model — exactly what the user
        wants to preview.

        Standard mode: flatten and upload directly (already in Roblox-UV space).
        """
        canvas = self._canvas_widget.canvas

        if self._advanced_mode:
            # Flatten ALL visible layers — guide + paint layers together.
            # advanced_to_roblox() will sample every ADV_REGION cell from this
            # composite and paste it into the correct Roblox UV position.
            flat = canvas.flatten()
            from core.advanced_template import advanced_to_roblox
            flat = advanced_to_roblox(flat, tmpl_type=self._template_type)
        else:
            flat = canvas.flatten()

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
            # Remove recovery file after a clean manual save
            try:
                if self._autosave_path and os.path.exists(self._autosave_path):
                    os.remove(self._autosave_path)
            except Exception:
                pass
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

    def _on_export_roblox(self) -> None:
        """Export a Roblox-ready 585×559 PNG with a preview dialog."""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
        from PyQt6.QtGui import QPixmap as _QP
        from PyQt6.QtCore import Qt as _Qt
        import tempfile

        flat = self._canvas.flatten()

        # Show quick preview dialog
        dlg = QDialog(self)
        dlg.setWindowTitle("Export for Roblox")
        dlg.setMinimumWidth(420)
        vl = QVBoxLayout(dlg)

        info = QLabel(
            "<b>Ready to export for Roblox</b><br>"
            "The texture will be saved as a 585×559 PNG.<br>"
            "Upload it to Roblox Studio → Explorer → Shirt/Pants → ShirtTemplate."
        )
        info.setWordWrap(True)
        vl.addWidget(info)

        # Preview thumbnail
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            tmp = tf.name
        flat.save(tmp)
        thumb = _QP(tmp).scaledToWidth(380, _Qt.TransformationMode.SmoothTransformation)
        os.unlink(tmp)
        prev_lbl = QLabel(); prev_lbl.setPixmap(thumb)
        prev_lbl.setAlignment(_Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(prev_lbl)

        hl = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dlg.reject)
        save_btn = QPushButton("Save PNG…")
        save_btn.setDefault(True)
        save_btn.clicked.connect(dlg.accept)
        hl.addWidget(cancel_btn); hl.addWidget(save_btn)
        vl.addLayout(hl)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export for Roblox", "roblox_shirt.png", "PNG Image (*.png)"
        )
        if path:
            try:
                from core.project_io import export_texture
                export_texture(self._canvas, path, self._template_type)
                self._status_label.setText(f"Exported for Roblox: {os.path.basename(path)}")
                QMessageBox.information(self, "Exported!",
                    f"Saved to:\n{path}\n\nUpload this file to Roblox Studio.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Export failed:\n{e}")

    # ── Advanced template ────────────────────────────────────────────────────

    def _new_advanced_template(self, tmpl_type: str = "shirt") -> None:
        """Create a new canvas pre-loaded with the Dripzels advanced template guide PNG."""
        if self._dirty and not self._confirm_discard():
            return
        import numpy as np
        from PIL import Image as PILImage
        w, h = 585, 559
        self._canvas = CanvasState(width=w, height=h)

        # Layer 1: blank painting canvas (bottom — user paints here)
        self._canvas.add_layer("Background")

        # Layer 2: the actual Dripzels advanced template PNG as a locked reference
        guide = self._canvas.add_layer("Advanced UV Guide")
        _tmpl_path = resource_path("assets", "templates", "advanced_template.png")
        try:
            _tmpl_img = PILImage.open(_tmpl_path).convert("RGBA").resize((w, h), PILImage.LANCZOS)
            guide.pixels = np.array(_tmpl_img, dtype=np.uint8)
        except Exception:
            # Fallback: generated colour overlay if PNG missing
            from core.advanced_template import draw_uv_overlay
            _tmpl_img = draw_uv_overlay(w, h, mode="advanced")
            guide.pixels = np.array(_tmpl_img, dtype=np.uint8)
        guide.opacity = 0.85
        guide.locked = True

        # Layer 3: active paint layer
        self._canvas.add_layer("Layer 1")
        self._canvas.active_layer_index = 2

        self._canvas_widget.canvas = self._canvas
        self._canvas_widget._invalidate_cache()
        self._layer_panel._canvas = self._canvas
        self._layer_panel.refresh()
        self._template_type = tmpl_type
        self._advanced_mode = True
        self._project_path = None
        self._dirty = False
        self._update_title()
        self._status_label.setText(
            "Advanced template loaded — paint inside the UV regions, "
            "then Canvas → Export Advanced → Roblox Upload to convert.")

    def _on_uv_overlay(self, checked: bool) -> None:
        """Toggle UV region overlay on/off."""
        from core.advanced_template import draw_uv_overlay
        import numpy as np
        # Find or create the UV Guide layer
        for layer in self._canvas.layers:
            if layer.name == "Advanced UV Guide":
                layer.visible = checked
                self._canvas_widget._invalidate_cache()
                self._layer_panel.refresh()
                self._push_texture_to_3d()
                return
        if checked:
            # Create one on the fly
            guide = self._canvas.add_layer("Advanced UV Guide")
            overlay_img = draw_uv_overlay(self._canvas.width,
                                          self._canvas.height, mode="advanced")
            guide.pixels = np.array(overlay_img, dtype=np.uint8)
            guide.opacity = 0.75
            guide.locked = True
            # Move to top
            self._canvas.layers.append(self._canvas.layers.pop(
                self._canvas.layers.index(guide)))
            self._canvas_widget._invalidate_cache()
            self._layer_panel.refresh()

    def _on_export_advanced(self) -> None:
        """Convert advanced-layout canvas to official Roblox 585x559 and export."""
        from core.advanced_template import advanced_to_roblox
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
        from PyQt6.QtGui import QPixmap as _QP
        from PyQt6.QtCore import Qt as _Qt
        import tempfile

        # Flatten canvas (hide UV guide layer for export)
        vis_states = {}
        for layer in self._canvas.layers:
            if layer.name == "Advanced UV Guide":
                vis_states[id(layer)] = layer.visible
                layer.visible = False
        flat = self._canvas_widget.canvas.flatten()
        for layer in self._canvas.layers:
            if id(layer) in vis_states:
                layer.visible = vis_states[id(layer)]

        converted = advanced_to_roblox(flat, tmpl_type=self._template_type)

        # Preview dialog
        dlg = QDialog(self)
        dlg.setWindowTitle("Export Advanced → Roblox")
        dlg.setMinimumWidth(500)
        vl = QVBoxLayout(dlg)

        info = QLabel(
            "<b>Advanced Template → Roblox Conversion</b><br>"
            "Your painting will be remapped from the advanced UV layout<br>"
            "to the official Roblox 585×559 shirt format."
        )
        info.setWordWrap(True)
        vl.addWidget(info)

        # Side-by-side preview
        hl_prev = QHBoxLayout()
        for title, img in [("Your Design (Advanced)", flat),
                            ("Converted (Roblox Upload)", converted)]:
            col = QVBoxLayout()
            lbl = QLabel(title); lbl.setAlignment(_Qt.AlignmentFlag.AlignCenter)
            col.addWidget(lbl)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
                img.save(tf.name)
                pix = _QP(tf.name).scaledToWidth(220,
                    _Qt.TransformationMode.SmoothTransformation)
            img_lbl = QLabel(); img_lbl.setPixmap(pix)
            img_lbl.setAlignment(_Qt.AlignmentFlag.AlignCenter)
            col.addWidget(img_lbl)
            hl_prev.addLayout(col)
        vl.addLayout(hl_prev)

        hl = QHBoxLayout()
        cancel_btn = QPushButton("Cancel"); cancel_btn.clicked.connect(dlg.reject)
        save_btn = QPushButton("Save Roblox PNG…"); save_btn.setDefault(True)
        save_btn.clicked.connect(dlg.accept)
        hl.addWidget(cancel_btn); hl.addWidget(save_btn)
        vl.addLayout(hl)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Roblox Upload PNG",
            "roblox_shirt_upload.png", "PNG Image (*.png)")
        if path:
            try:
                converted.save(path, format="PNG")
                self._status_label.setText(
                    f"Exported Roblox-ready PNG: {os.path.basename(path)}")
                QMessageBox.information(self, "Done!",
                    f"Saved to:\n{path}\n\nUpload this to Roblox Studio.")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _on_symmetry(self, val: str) -> None:
        from core.models import SymmetryAxis as _SA
        axis_map = {"none": _SA.NONE, "horizontal": _SA.HORIZONTAL,
                    "vertical": _SA.VERTICAL, "both": _SA.BOTH}
        self._tools.symmetry_axis = axis_map.get(val, _SA.NONE)
        # Update checkmarks
        for act in self._sym_menu.actions():
            act.setChecked(act.data() == val)
        self._canvas_widget.update()
        self._status_label.setText(f"Symmetry: {val.title()}")

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
            import tempfile
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
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QScrollArea, QWidget, QPushButton
        from PyQt6.QtCore import Qt as _Qt

        dlg = QDialog(self)
        dlg.setWindowTitle("Keyboard Shortcuts")
        dlg.setMinimumWidth(480)
        dlg.setMinimumHeight(540)
        dlg.setStyleSheet("background:#1e1e2e; color:#cdd6f4; font-size:10pt;")

        outer = QVBoxLayout(dlg)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        content = QWidget()
        vl = QVBoxLayout(content)
        vl.setSpacing(2)

        def section(title):
            lbl = QLabel(f"<b style='color:#89b4fa;font-size:11pt;'>{title}</b>")
            vl.addSpacing(8)
            vl.addWidget(lbl)

        def row(keys, desc):
            from PyQt6.QtWidgets import QHBoxLayout
            hl = QHBoxLayout(); hl.setSpacing(0)
            k_lbl = QLabel(keys)
            k_lbl.setStyleSheet(
                "background:#313244;color:#cba6f7;border-radius:4px;"
                "padding:2px 8px;font-family:monospace;font-size:9pt;")
            k_lbl.setFixedWidth(170)
            d_lbl = QLabel(desc)
            d_lbl.setStyleSheet("color:#cdd6f4; padding-left:10px;")
            hl.addWidget(k_lbl); hl.addWidget(d_lbl, 1)
            w = QWidget(); w.setLayout(hl)
            vl.addWidget(w)

        section("🖌  Tools")
        row("B",              "Brush")
        row("E",              "Eraser")
        row("G",              "Fill / Bucket")
        row("I",              "Eyedropper")
        row("S",              "Selection")
        row("R",              "Rectangle")
        row("C",              "Ellipse")
        row("L",              "Line")
        row("T",              "Text")
        row("V",              "Transform")

        section("📋  Selection")
        row("Ctrl + A",       "Select All")
        row("Ctrl + D",       "Deselect")
        row("Ctrl + C",       "Copy Selection")
        row("Ctrl + X",       "Cut Selection")
        row("Ctrl + V",       "Paste")
        row("Delete",         "Delete Selected Pixels")
        row("Escape",         "Drop Float / Deselect")

        section("📁  File")
        row("Ctrl + N",       "New Project")
        row("Ctrl + O",       "Open Project")
        row("Ctrl + S",       "Save Project")
        row("Ctrl + Shift + S","Save As…")
        row("Ctrl + I",       "Import Image as Layer")
        row("Ctrl + E",       "Export Texture PNG")
        row("Ctrl + Shift + E","Export for Roblox Upload")

        section("✏️  Edit")
        row("Ctrl + Z",       "Undo")
        row("Ctrl + Y",       "Redo")
        row("Delete",         "Clear Active Layer (no selection)")
        row("Ctrl + Shift + A","Apply Transform")

        section("🔍  View")
        row("=  /  -",        "Zoom In / Zoom Out")
        row("0",              "Fit Canvas to Window")
        row("1",              "Zoom to 100%")
        row("Middle Mouse",   "Pan Canvas")
        row("Scroll Wheel",   "Zoom In / Out")

        section("🎨  Text Tool")
        row("Click (empty)",  "Place new text object")
        row("Click (text)",   "Select & drag text")
        row("Double-click",   "Edit text content")
        row("Enter",          "Bake text into layer")
        row("Delete",         "Bake & remove text")

        section("🔁  Symmetry  (Tool Options panel)")
        row("H ↔",            "Mirror strokes horizontally")
        row("V ↕",            "Mirror strokes vertically")
        row("✛ Both",         "Mirror in both axes")

        vl.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(28)
        close_btn.setStyleSheet(
            "QPushButton{background:#313244;color:#cdd6f4;border:1px solid #454565;"
            "border-radius:4px;padding:0 16px;font-size:10pt;}"
            "QPushButton:hover{background:#3a4a80;}")
        close_btn.clicked.connect(dlg.accept)
        outer.addWidget(close_btn)

        dlg.exec()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def keyPressEvent(self, event) -> None:
        """Forward all shortcuts to canvas widget regardless of focus."""
        from PyQt6.QtCore import Qt as _Qt
        key   = event.key()
        ctrl  = bool(event.modifiers() & _Qt.KeyboardModifier.ControlModifier)
        shift = bool(event.modifiers() & _Qt.KeyboardModifier.ShiftModifier)
        cw    = self._canvas_widget

        # Selection
        if ctrl and key == _Qt.Key.Key_A:
            cw.select_all(); return
        if ctrl and key == _Qt.Key.Key_D:
            cw.clear_selection(); return
        if ctrl and key == _Qt.Key.Key_C:
            cw.copy_selection(); return
        if ctrl and key == _Qt.Key.Key_X:
            cw.cut_selection(); return
        if ctrl and key == _Qt.Key.Key_V:
            cw.paste_selection(); return
        if key == _Qt.Key.Key_Delete:
            if cw._tools.tool.value == "select":
                cw.delete_selection(); return
        if key == _Qt.Key.Key_Escape:
            cw.clear_selection(); return

        # Undo / Redo
        if ctrl and key == _Qt.Key.Key_Z:
            cw.undo(); return
        if ctrl and (key == _Qt.Key.Key_Y or (shift and key == _Qt.Key.Key_Z)):
            cw.redo(); return

        super().keyPressEvent(event)

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
        # Stop auto-save timer and clean up recovery file on normal exit
        if hasattr(self, '_autosave_timer') and self._autosave_timer:
            self._autosave_timer.stop()
        if not self._dirty:
            try:
                if self._autosave_path and os.path.exists(self._autosave_path):
                    os.remove(self._autosave_path)
            except Exception:
                pass
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
