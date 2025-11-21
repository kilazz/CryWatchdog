# app/utils.py
import html
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from lxml import etree as ET
from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from app.config import UIConfig


class CoreSignals(QObject):
    """Defines signals for communication from background tasks to the GUI thread."""

    log = Signal(str)
    indexingStarted = Signal()
    indexingFinished = Signal()
    taskFinished = Signal(object)
    criticalError = Signal(str, str)
    watcherStopped = Signal()
    progressUpdated = Signal(int, int)


class Worker(QRunnable):
    """A generic QRunnable worker for executing a function in the QThreadPool."""

    def __init__(self, fn: Callable, *args: Any, **kwargs: Any):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = CoreSignals()

    @Slot()
    def run(self):
        """Executes the target function and emits signals based on the outcome."""
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.signals.taskFinished.emit(result)
        except Exception as e:
            logging.error(f"Error in worker thread: {e}", exc_info=True)
            self.signals.criticalError.emit("Task Error", f"A critical error occurred: {e}")


def atomic_write(file_path: Path, data: Any, **kwargs: Any):
    """Writes data to a temporary file and then atomically replaces the original."""
    temp_path = file_path.with_suffix(file_path.suffix + ".tmp")
    try:
        if isinstance(data, str):
            temp_path.write_text(data, **kwargs)
        elif isinstance(data, bytes):
            temp_path.write_bytes(data)
        elif isinstance(data, ET._ElementTree):
            data.write(str(temp_path), **kwargs)
        else:
            raise TypeError(f"Unsupported data type for atomic_write: {type(data)}")
        os.replace(temp_path, file_path)
    except Exception as e:
        logging.error(f"Atomic write to {file_path} failed: {e}")
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise


def find_files_by_extensions(root_path: Path, extensions: tuple[str, ...]) -> list[Path]:
    """Recursively finds all files with given extensions in a directory."""
    return [
        Path(root) / filename
        for root, _, files in os.walk(root_path)
        for filename in files
        if filename.lower().endswith(extensions)
    ]


class QtLogHandler(logging.Handler):
    """A logging handler that emits a Qt signal for each log record."""

    class LogSignals(QObject):
        log = Signal(str)

    def __init__(self):
        super().__init__()
        self.signals = self.LogSignals()

    def emit(self, record):
        """Emits the formatted log record via a signal as an HTML string."""
        level_map = {
            logging.DEBUG: "color: gray;",
            logging.INFO: "color: white;",
            logging.WARNING: f"color: {UIConfig.COLOR_WARNING};",
            logging.ERROR: f"color: {UIConfig.COLOR_ERROR};",
            logging.CRITICAL: f"color: {UIConfig.COLOR_ERROR}; font-weight: bold;",
        }
        style = level_map.get(record.levelno, "color: white;")
        formatted_message = html.escape(self.format(record))
        self.signals.log.emit(f'<span style="{style}">{formatted_message}</span>')
