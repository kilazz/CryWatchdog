# app/core/signals.py
from PySide6.QtCore import QObject, Signal


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
