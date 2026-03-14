import logging
import traceback

from PySide6.QtCore import QObject, QThreadPool, Signal
from PySide6.QtWidgets import QMessageBox

from app.config import AppState
from app.core.worker import Worker


class TaskManager(QObject):
    stateChanged = Signal(AppState)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool()
        self._active_workers = set()
        self.parent_widget = parent

    def can_run_task(self, current_state: AppState, require_project=True, has_project=False):
        if current_state != AppState.IDLE:
            if self.parent_widget:
                QMessageBox.warning(self.parent_widget, "Wait", "Another operation is in progress.")
            return False

        if require_project and not has_project:
            if self.parent_widget:
                QMessageBox.warning(self.parent_widget, "Warning", "Please select a project folder first.")
            return False

        return True

    def run_task(self, func, callback=None, error_callback=None):
        self.stateChanged.emit(AppState.TASK_RUNNING)

        worker = Worker(func)
        self._active_workers.add(worker)

        def done(res):
            try:
                self._active_workers.discard(worker)
                if callback:
                    callback(res)
            except Exception as e:
                logging.error(f"Error in task callback: {e}")
                traceback.print_exc()
                if self.parent_widget:
                    QMessageBox.critical(self.parent_widget, "Callback Error", f"An error occurred after the task finished:\n{e}")
            finally:
                self.stateChanged.emit(AppState.IDLE)

        def error_handler(title, message):
            self._active_workers.discard(worker)
            if error_callback:
                error_callback(title, message)
            else:
                if self.parent_widget:
                    QMessageBox.critical(self.parent_widget, title, message)
            self.stateChanged.emit(AppState.IDLE)

        worker.signals.taskFinished.connect(done)
        worker.signals.criticalError.connect(error_handler)

        self.pool.start(worker)

    def wait_for_done(self, msecs=500):
        self.pool.waitForDone(msecs)
