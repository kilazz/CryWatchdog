import logging
import sys
from multiprocessing import freeze_support


class StreamFilter:
    def __init__(self, stream):
        self.stream = stream

    def write(self, data: str):
        if "QFluentWidgets Pro" not in data and "📢 Tips:" not in data:
            self.stream.write(data)

    def flush(self):
        self.stream.flush()


sys.stdout = StreamFilter(sys.stdout)
sys.stderr = StreamFilter(sys.stderr)

logger = logging.getLogger(__name__)


def main():
    freeze_support()

    def exception_hook(exctype, value, tb):
        logger.critical("Uncaught exception", exc_info=(exctype, value, tb))
        sys.__excepthook__(exctype, value, tb)

    sys.excepthook = exception_hook

    try:
        from PySide6.QtWidgets import QApplication
        from qfluentwidgets import Theme, setTheme
    except ImportError as e:
        missing_lib = str(e).split("'")[-2] if "'" in str(e) else str(e)
        error_message = (
            f"ERROR: Missing required library '{missing_lib}'.\n\n"
            "Please install all dependencies from your pyproject.toml:\n"
            "uv pip install -e ."
        )
        print(error_message, file=sys.stderr)
        sys.exit(1)

    from app.core.logging import QtLogHandler, setup_logging
    from app.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    setTheme(Theme.DARK)

    main_window = MainWindow()

    log_handler = QtLogHandler()
    log_handler.signals.log.connect(main_window.append_log)

    setup_logging(log_handler)

    main_window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
