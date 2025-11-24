# app/utils.py
import html
import logging
import os
import stat
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from lxml import etree as ET
from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from app.config import UIConfig


class CoreSignals(QObject):
    """
    Defines the signals used for communication between worker threads
    and the main GUI thread.
    """

    log = Signal(str)
    indexingStarted = Signal()
    indexingFinished = Signal()
    taskFinished = Signal(object)
    criticalError = Signal(str, str)
    watcherStopped = Signal()
    progressUpdated = Signal(int, int)


class Worker(QRunnable):
    """
    Generic worker thread for running tasks in the background.
    """

    def __init__(self, fn: Callable, *args: Any, **kwargs: Any):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = CoreSignals()

    @Slot()
    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.signals.taskFinished.emit(result)
        except Exception as e:
            logging.error(f"Error in worker thread: {e}", exc_info=True)
            self.signals.criticalError.emit("Task Error", f"A critical error occurred: {e}")


def ensure_writable(file_path: Path):
    """
    Attempts to make a file writable using Perforce (P4) or OS chmod.
    Critical for working in game dev environments (Perforce/Git) where files
    might be Read-Only.
    """
    if not file_path.exists():
        return

    # If already writable, skip
    if os.access(file_path, os.W_OK):
        return

    # 1. Try Perforce (P4) checkout
    try:
        # Check if 'p4' is available and file is tracked
        proc = subprocess.run(
            ["p4", "edit", str(file_path)],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if proc.returncode == 0:
            logging.info(f"Checked out file via P4: {file_path.name}")
            return
    except FileNotFoundError:
        pass  # P4 not installed or not in PATH

    # 2. Fallback: Force OS write attribute (Git/Local)
    try:
        os.chmod(file_path, stat.S_IWRITE)
        logging.info(f"Removed Read-Only attribute: {file_path.name}")
    except Exception as e:
        logging.warning(f"Failed to make {file_path.name} writable: {e}")


def atomic_write(file_path: Path, data: Any, **kwargs: Any):
    """
    Writes data to a temp file, ensures the target is writable, then replaces it.
    Uses standard 'open()' instead of 'write_text' to ensure the 'newline'
    parameter is correctly applied on all Python versions/platforms.
    """
    temp_path = file_path.with_suffix(file_path.suffix + ".tmp")
    try:
        # Prepare temp file
        if isinstance(data, str):
            # Extract arguments specifically for open()
            encoding = kwargs.get("encoding", "utf-8")
            newline = kwargs.get("newline")

            # Use open() context manager to strictly control line endings
            with open(temp_path, "w", encoding=encoding, newline=newline) as f:
                f.write(data)

        elif isinstance(data, bytes):
            temp_path.write_bytes(data)
        elif isinstance(data, ET._ElementTree):
            data.write(str(temp_path), **kwargs)
        else:
            raise TypeError(f"Unsupported data type: {type(data)}")

        # Ensure target is writable (P4/Git support)
        if file_path.exists():
            ensure_writable(file_path)

        # Atomic replace
        os.replace(temp_path, file_path)

    except Exception as e:
        logging.error(f"Atomic write to {file_path} failed: {e}")
        # Clean up temp file on failure
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise


def find_files_by_extensions(root_path: Path, extensions: tuple[str, ...]) -> list[Path]:
    """
    Recursively finds all files in root_path matching the given extensions.
    """
    return [
        Path(root) / filename
        for root, _, files in os.walk(root_path)
        for filename in files
        if filename.lower().endswith(extensions)
    ]


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
        formatted_message = html.escape(self.format(record))
        self.signals.log.emit(f'<span style="{style}">{formatted_message}</span>')
