from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QRunnable, Slot

from app.core.signals import CoreSignals

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


class Worker(QRunnable):
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
            logger.error(f"Error in worker thread: {e}", exc_info=True)
            self.signals.criticalError.emit("Task Error", f"A critical error occurred: {e}")
