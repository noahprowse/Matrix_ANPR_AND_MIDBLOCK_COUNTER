"""Matrix Traffic Data Extraction — Desktop Application Entry Point."""

import logging
import os
import sys

# Fix PyTorch DLL loading on Windows — must run before any torch import
if sys.platform == "win32":
    _torch_lib = os.path.join(
        sys.prefix, "Lib", "site-packages", "torch", "lib"
    )
    if os.path.isdir(_torch_lib):
        os.add_dll_directory(_torch_lib)
    # Force early torch import so DLL is loaded for all threads
    try:
        import torch  # noqa: F401
    except Exception:
        pass

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

from src.app import MainWindow
from src.common.theme import APP_STYLESHEET


def _setup_logging() -> None:
    """Configure application-wide logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    # Suppress noisy third-party loggers
    logging.getLogger("ultralytics").setLevel(logging.WARNING)
    logging.getLogger("ppocr").setLevel(logging.WARNING)
    logging.getLogger("paddle").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)


def main() -> None:
    _setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting Matrix Traffic Data Extraction v3.0.0")

    app = QApplication(sys.argv)

    # Global stylesheet
    app.setStyleSheet(APP_STYLESHEET)

    # Default font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Create and show main window
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
