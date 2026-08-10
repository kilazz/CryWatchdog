import html
import logging
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import QObject, Signal, qInstallMessageHandler

from app.config import AppConfig, UIConfig

logger = logging.getLogger(__name__)


def _qt_message_handler(msg_type, context, message):
    # Filter out harmless Qt internal C++ font/stylesheet warnings
    if "QFont::setPointSize" in message or "Point size <= 0" in message:
        return


class QtLogHandler(logging.Handler):
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

        msg = self.format(record)
        formatted_message = html.escape(msg)
        self.signals.log.emit(f'<span style="{style}">{formatted_message}</span>')


def setup_logging(qt_handler: QtLogHandler):
    qInstallMessageHandler(_qt_message_handler)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    file_fmt = logging.Formatter("%(asctime)s [%(levelname)s] [%(threadName)s] %(name)s: %(message)s")
    gui_fmt = logging.Formatter("%(asctime)s - %(levelname)-7s - %(message)s", datefmt="%H:%M:%S")

    qt_handler.setFormatter(gui_fmt)
    root_logger.addHandler(qt_handler)

    log_dir = AppConfig.PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "debug.log"

    file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(file_fmt)
    file_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(file_fmt)
    root_logger.addHandler(console_handler)

    logger.info(f"Logging initialized. Log file: {log_file}")
