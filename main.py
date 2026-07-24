"""Ruki's Music Transcriber application entry point."""

import sys

from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


def main() -> int:
    """Create the Qt application and show the main window."""
    application = QApplication(sys.argv)
    application.setApplicationName("Ruki's Music Transcriber")
    application.setOrganizationName("Ruki Music Lab")
    application.setStyle("Fusion")

    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
