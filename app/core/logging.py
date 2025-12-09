# app/core/logging.py
import html
import logging
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import QObject, Signal

from app.config import AppConfig, UIConfig


class QtLogHandler(logging.Handler):
    """
    Custom logging handler that emits a Qt signal for every log record,
    allowing logs to be displayed in the GUI with HTML formatting.
    """

    class LogSignals(QObject):
        log = Signal(str)

    def __init__(self):
        super().__init__()
        self.signals = self.LogSignals()

    def emit(self, record):
        level_map = {
            logging.DEBUG: "color: gray;",
            logging.INFO: "color: white;",
            logging.WARNING: f"color: {UIConfig.COLOR_WARNING};",
            logging.ERROR: f"color: {UIConfig.COLOR_ERROR};",
            logging.CRITICAL: f"color: {UIConfig.COLOR_ERROR}; font-weight: bold;",
        }

        style = level_map.get(record.levelno, "color: white;")
        if "[DRY RUN]" in record.getMessage():
            style = f"color: {UIConfig.COLOR_DRY_RUN}; font-weight: bold;"

        # Format just the message for the GUI
        msg = self.format(record)
        formatted_message = html.escape(msg)
        self.signals.log.emit(f'<span style="{style}">{formatted_message}</span>')


def setup_logging(qt_handler: QtLogHandler):
    """
    Configures root logger to write to:
    1. The GUI (via qt_handler)
    2. A file (logs/app.log)
    3. The console (stdout)
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)  # Default level

    # Formatters
    file_fmt = logging.Formatter("%(asctime)s [%(levelname)s] [%(threadName)s] %(name)s: %(message)s")
    gui_fmt = logging.Formatter("%(asctime)s - %(levelname)-7s - %(message)s", datefmt="%H:%M:%S")

    # 1. GUI Handler
    qt_handler.setFormatter(gui_fmt)
    root_logger.addHandler(qt_handler)

    # 2. File Handler (Rotating)
    log_dir = AppConfig.PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "debug.log"

    file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(file_fmt)
    # File always records DEBUG info, regardless of UI settings
    file_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)

    # 3. Console Handler (for IDE/CMD debugging)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(file_fmt)
    root_logger.addHandler(console_handler)

    logging.info(f"Logging initialized. Log file: {log_file}")
