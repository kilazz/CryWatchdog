# app/core/worker.py
import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QRunnable, Slot

from app.core.signals import CoreSignals


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
