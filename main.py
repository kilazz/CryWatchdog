# main.py
import logging
import sys

# --- Dependency Checks ---
try:
    import qdarkstyle
    from PySide6.QtWidgets import QApplication, QMessageBox
except ImportError as e:
    # This block handles missing critical libraries gracefully.
    missing_lib = str(e).split("'")[-2]
    error_message = (
        f"ERROR: Missing required library '{missing_lib}'.\n\n"
        "Please install all dependencies from your pyproject.toml, for example:\n"
        "pip install -e ."
    )
    print(error_message, file=sys.stderr)
    # Attempt to show a GUI message box if possible.
    try:
        app = QApplication(sys.argv)
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setText(error_message)
        msg_box.setWindowTitle("Dependency Error")
        msg_box.exec()
    except Exception:
        pass  # Fallback to console output if GUI fails
    sys.exit(1)

# Import application components after dependency check
from app.main_window import MainWindow
from app.utils import QtLogHandler


def setup_logging(log_handler: QtLogHandler):
    """
    Configures the Python logging module to route all log messages
    to the GUI's log view via the provided QtLogHandler.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)-7s - %(message)s",
        datefmt="%H:%M:%S",
        handlers=[log_handler],
        force=True,  # Overwrite any existing root logger configuration
    )


def main():
    """
    Initializes and runs the AssetWatchdog application.
    This is the main entry point.
    """
    app = QApplication(sys.argv)
    app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api="pyside6"))

    # Create the main window instance
    main_window = MainWindow()

    # Create the log handler and connect its signal to the main window's slot
    log_handler = QtLogHandler()
    log_handler.signals.log.connect(main_window.append_log)

    # Configure the root logger to use our custom handler
    setup_logging(log_handler)

    # Show the main window and start the application event loop
    main_window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
