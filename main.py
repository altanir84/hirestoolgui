#!/usr/bin/env python3
"""
Entry point for the HiResToolsGUI.

Usage:
    python3 main.py
"""

import sys
from pathlib import Path

# Ensure the project root is on sys.path so that "app.*" imports work
# regardless of where the script is invoked from.
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

from app.main_window import MainWindow
from app.utils.resources import resource_path


def main() -> None:
    """Bootstrap the Qt application and show the main window."""
    app = QApplication(sys.argv)
    app.setApplicationName("HiResToolsGUI")
    app.setOrganizationName("HiResToolsGUI")
    app.setApplicationVersion("1.0.0")
    app.setWindowIcon(QIcon(str(resource_path("assets/hires_toolgui.svg"))))

    # Detect system dark-mode preference (Qt 6.5+).
    # Fall back to a dark palette on older versions.
    try:
        from PySide6.QtGui import QStyleHints  # noqa: WPS433
        if app.styleHints().colorScheme() == Qt.ColorScheme.Dark:
            app.setStyle("Fusion")
    except AttributeError:
        app.setStyle("Fusion")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":

    main()


