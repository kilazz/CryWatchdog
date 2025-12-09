# main.py
import logging
import sys
from multiprocessing import freeze_support

# --- Dependency Checks ---
try:
    import qdarkstyle
    from PySide6.QtWidgets import QApplication, QMessageBox
except ImportError as e:
    # Gracefully handle missing dependencies
    missing_lib = str(e).split("'")[-2]
    error_message = (
        f"ERROR: Missing required library '{missing_lib}'.\n\n"
        "Please install all dependencies from your pyproject.toml, for example:\n"
        "pip install -e ."
    )
    print(error_message, file=sys.stderr)
    # Try to show a GUI message box
    try:
        app = QApplication(sys.argv)
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setText(error_message)
        msg_box.setWindowTitle("Dependency Error")
        msg_box.exec()
    except Exception:
        pass
    sys.exit(1)

# Import application components after dependency check
from app.core.logging import QtLogHandler, setup_logging
from app.ui.main_window import MainWindow


def main():
    """
    Initializes and runs the CryWatchdog application.
    """
    # CRITICAL: Fixes recursive process spawning on Windows when using ProcessPoolExecutor/ThreadPoolExecutor
    # This must be the very first line in main() to prevent the application from spawning infinite copies of itself.
    freeze_support()

    # Global Exception Hook to catch crashes and log them to file/console
    # This ensures that "silent crashes" are recorded in logs/debug.log
    def exception_hook(exctype, value, tb):
        logging.critical("Uncaught exception", exc_info=(exctype, value, tb))
        sys.__excepthook__(exctype, value, tb)

    sys.excepthook = exception_hook

    app = QApplication(sys.argv)
    app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api="pyside6"))

    # Create the main window instance
    main_window = MainWindow()

    # Create the log handler and connect its signal to the main window's slot
    log_handler = QtLogHandler()
    log_handler.signals.log.connect(main_window.append_log)

    # Configure the root logger (File + Console + GUI)
    setup_logging(log_handler)

    # Show the main window and start the application event loop
    main_window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
