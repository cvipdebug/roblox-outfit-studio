"""
Roblox Outfit Studio - Main Entry Point
A Python rewrite and extension of SlothX Outfit Viewer with full 2D clothing editor.
"""

import sys
import os

# Ensure src directory is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from ui.main_window import MainWindow


from core.resources import resource_path

def main() -> None:
    """Launch the Roblox Outfit Studio application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Roblox Outfit Studio")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("OutfitStudio")

    # Set application icon (works in taskbar, window title, alt-tab)
    icon_path = resource_path("assets", "icon.ico")
    if not os.path.exists(icon_path):
        icon_path = resource_path("assets", "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Theme is applied by ThemeManager inside MainWindow

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


def _get_stylesheet() -> str:
    """Return the application-wide dark theme stylesheet."""
    return """
    QMainWindow, QWidget {
        background-color: #1e1e2e;
        color: #cdd6f4;
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 13px;
    }
    QMenuBar {
        background-color: #181825;
        color: #cdd6f4;
        border-bottom: 1px solid #313244;
    }
    QMenuBar::item:selected {
        background-color: #313244;
    }
    QMenu {
        background-color: #181825;
        border: 1px solid #313244;
    }
    QMenu::item:selected {
        background-color: #45475a;
    }
    QToolBar {
        background-color: #181825;
        border-bottom: 1px solid #313244;
        spacing: 4px;
        padding: 4px;
    }
    QToolButton {
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 4px;
        padding: 4px;
        color: #cdd6f4;
    }
    QToolButton:hover {
        background-color: #313244;
        border-color: #45475a;
    }
    QToolButton:checked {
        background-color: #89b4fa;
        color: #1e1e2e;
        border-color: #89b4fa;
    }
    QDockWidget {
        titlebar-close-icon: none;
        color: #cdd6f4;
    }
    QDockWidget::title {
        background-color: #181825;
        padding: 6px;
        border-bottom: 1px solid #313244;
        text-align: left;
    }
    QSlider::groove:horizontal {
        height: 4px;
        background: #313244;
        border-radius: 2px;
    }
    QSlider::handle:horizontal {
        background: #89b4fa;
        width: 14px;
        height: 14px;
        margin: -5px 0;
        border-radius: 7px;
    }
    QSlider::sub-page:horizontal {
        background: #89b4fa;
        border-radius: 2px;
    }
    QPushButton {
        background-color: #313244;
        border: 1px solid #45475a;
        border-radius: 4px;
        padding: 5px 12px;
        color: #cdd6f4;
    }
    QPushButton:hover {
        background-color: #45475a;
    }
    QPushButton:pressed {
        background-color: #89b4fa;
        color: #1e1e2e;
    }
    QListWidget {
        background-color: #181825;
        border: 1px solid #313244;
        border-radius: 4px;
    }
    QListWidget::item:selected {
        background-color: #45475a;
    }
    QListWidget::item:hover {
        background-color: #313244;
    }
    QScrollBar:vertical {
        background: #181825;
        width: 10px;
        border-radius: 5px;
    }
    QScrollBar::handle:vertical {
        background: #45475a;
        border-radius: 5px;
        min-height: 20px;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0;
    }
    QComboBox {
        background-color: #313244;
        border: 1px solid #45475a;
        border-radius: 4px;
        padding: 3px 8px;
        color: #cdd6f4;
    }
    QComboBox::drop-down {
        border: none;
    }
    QComboBox QAbstractItemView {
        background-color: #181825;
        border: 1px solid #313244;
        selection-background-color: #45475a;
    }
    QSpinBox, QDoubleSpinBox {
        background-color: #313244;
        border: 1px solid #45475a;
        border-radius: 4px;
        padding: 3px 6px;
        color: #cdd6f4;
    }
    QLabel {
        color: #cdd6f4;
    }
    QGroupBox {
        border: 1px solid #313244;
        border-radius: 4px;
        margin-top: 8px;
        padding-top: 4px;
        color: #a6adc8;
        font-size: 11px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 8px;
        padding: 0 4px;
    }
    QSplitter::handle {
        background-color: #313244;
        width: 2px;
        height: 2px;
    }
    QTabWidget::pane {
        border: 1px solid #313244;
    }
    QTabBar::tab {
        background-color: #181825;
        color: #a6adc8;
        padding: 6px 14px;
        border: 1px solid #313244;
        border-bottom: none;
    }
    QTabBar::tab:selected {
        background-color: #1e1e2e;
        color: #cdd6f4;
    }
    QStatusBar {
        background-color: #181825;
        color: #a6adc8;
        border-top: 1px solid #313244;
    }
    """


if __name__ == "__main__":
    main()
