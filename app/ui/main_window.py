# app/ui/main_window.py
import logging
import traceback
from collections import defaultdict
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.config import AppState, UIConfig
from app.core.signals import CoreSignals
from app.core.worker import Worker
from app.services.watcher import WatcherService

# Tasks
from app.tasks.analyzer import ProjectAnalyzer
from app.tasks.cleaner import ProjectCleaner
from app.tasks.converter import ProjectConverter
from app.tasks.duplicates import DuplicateFinder
from app.tasks.finding import MissingAssetFinder, UnusedAssetFinder
from app.tasks.texture_validator import TextureValidator
from app.tasks.tod import TimeOfDayConverter

# Dialogs
from app.ui.dialogs.cleaner_dlg import CleanerDialog
from app.ui.dialogs.duplicates_dlg import DuplicateFinderDialog
from app.ui.dialogs.finding_dlg import MissingAssetsDialog, UnusedAssetsDialog
from app.ui.dialogs.lua_dlg import LuaToolkitDialog
from app.ui.dialogs.packer_dlg import PackerDialog
from app.ui.dialogs.reports_dlg import AnalysisReportDialog
from app.ui.dialogs.texture_dlg import TextureReportDialog
from app.ui.dialogs.tod_dlg import TimeOfDayDialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CryWatchdog")
        self.setGeometry(100, 100, 1100, 700)
        self.project_root = None
        self.watcher_service = None
        self.state = AppState.IDLE
        self.pool = QThreadPool()
        self.core_signals = CoreSignals()

        # CRITICAL FIX: Keep references to active workers to prevent Garbage Collection
        # from destroying them before their signals reach the main thread.
        self._active_workers = set()

        self._init_ui()
        self._connect_core()
        self._set_state(AppState.IDLE)

    def _init_ui(self):
        w = QWidget()
        self.setCentralWidget(w)
        layout = QVBoxLayout(w)

        # --- Top Bar ---
        top = QHBoxLayout()
        self.btn_sel = QPushButton("Select Folder")
        self.btn_proj = QPushButton("Project")
        self.btn_util = QPushButton("Utils")
        self.lbl_status = QLabel("Select a project folder.")

        # Project Menu
        m_proj = QMenu(self)
        m_proj.addAction("Analyze...").triggered.connect(self._analyze)
        m_proj.addAction("Validate Textures...").triggered.connect(self._validate_textures)
        m_proj.addSeparator()
        m_proj.addAction("Find Unused...").triggered.connect(self._unused)
        m_proj.addAction("Find Missing...").triggered.connect(self._missing)
        m_proj.addSeparator()
        m_proj.addAction("Lua Tools...").triggered.connect(self._lua)
        m_proj.addAction("Clean Assets...").triggered.connect(self._clean)
        m_proj.addSeparator()
        m_proj.addAction("To Lowercase...").triggered.connect(self._convert_lc)
        self.btn_proj.setMenu(m_proj)

        # Utils Menu
        m_util = QMenu(self)
        m_util.addAction("Packer...").triggered.connect(self._pack)
        m_util.addSeparator()
        m_util.addAction("Duplicate Finder...").triggered.connect(self._dupes)
        m_util.addAction("TOD Converter...").triggered.connect(self._tod)
        self.btn_util.setMenu(m_util)

        top.addWidget(self.btn_sel)
        top.addWidget(self.btn_proj)
        top.addWidget(self.btn_util)
        top.addStretch()
        top.addWidget(self.lbl_status)
        layout.addLayout(top)

        # --- Watcher Group ---
        grp = QGroupBox("Real-time Watchdog")
        gl = QVBoxLayout(grp)
        ol = QHBoxLayout()
        self.opts = {}
        for k, t, d in [
            ("match_any_texture_extension", "Match Any Texture", True),
            ("allow_dir_change", "Patch Dir Moves", True),
            ("dry_run", "Dry Run", False),
            ("show_detailed_log", "Debug Log", False),
        ]:
            cb = QCheckBox(t)
            cb.setChecked(d)
            if k == "dry_run":
                cb.setStyleSheet(f"color: {UIConfig.COLOR_DRY_RUN}; font-weight: bold;")
            self.opts[k] = cb
            ol.addWidget(cb)
        self.btn_watch = QPushButton("Start Watchdog")
        gl.addLayout(ol)
        gl.addWidget(self.btn_watch)
        layout.addWidget(grp)

        # --- Log View ---
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(UIConfig.FONT_MONOSPACE)
        layout.addWidget(self.log)

        # --- Status Bar ---
        self.pbar = QProgressBar()
        self.statusBar().addPermanentWidget(self.pbar)
        self.pbar.hide()

        # Connect top-level buttons
        self.btn_sel.clicked.connect(self._select_folder)
        self.btn_watch.clicked.connect(self._toggle_watch)
        self.opts["show_detailed_log"].stateChanged.connect(self._toggle_log)

    def _connect_core(self):
        self.core_signals.indexingStarted.connect(lambda: self._set_state(AppState.INDEXING))
        self.core_signals.indexingFinished.connect(lambda: self._set_state(AppState.WATCHING))
        self.core_signals.watcherStopped.connect(lambda: self._set_state(AppState.IDLE))
        self.core_signals.criticalError.connect(self._error)
        self.core_signals.progressUpdated.connect(self._progress)

    def _set_state(self, s):
        self.state = s
        has_proj = bool(self.project_root)
        self.btn_sel.setEnabled(s == AppState.IDLE)
        self.btn_proj.setEnabled(s == AppState.IDLE and has_proj)
        self.btn_util.setEnabled(s == AppState.IDLE)

        txt, col = ("Start", UIConfig.COLOR_IDLE)
        if s == AppState.WATCHING:
            txt, col = ("Stop", UIConfig.COLOR_INFO)
        elif s == AppState.INDEXING:
            txt, col = ("Stop", UIConfig.COLOR_SUCCESS)
        elif s == AppState.TASK_RUNNING:
            txt, col = ("Busy", UIConfig.COLOR_WARNING)

        self.btn_watch.setText(txt)
        self.lbl_status.setStyleSheet(f"color: {col}")

        # Watcher button logic
        if s in [AppState.WATCHING, AppState.INDEXING] or (s == AppState.IDLE and has_proj):
            self.btn_watch.setEnabled(True)
        else:
            self.btn_watch.setEnabled(False)

        if s == AppState.TASK_RUNNING:
            self.pbar.show()
        else:
            self.pbar.hide()

    def _select_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Project Root")
        if d:
            self.project_root = Path(d)
            logging.info(f"Selected: {d}")
            self._set_state(AppState.IDLE)

    def _toggle_watch(self):
        if self.state in [AppState.WATCHING, AppState.INDEXING]:
            if self.watcher_service:
                self.watcher_service.stop()
        elif self.project_root:
            opts = {k: v.isChecked() for k, v in self.opts.items()}
            self.watcher_service = WatcherService(
                {"project_root": self.project_root, "watcher_options": opts}, self.core_signals
            )
            self.watcher_service.start()

    # --- Actions ---

    def can_run_task(self, require_project=True):
        if self.state != AppState.IDLE:
            QMessageBox.warning(self, "Wait", "Another operation is in progress.")
            return False

        if require_project and not self.project_root:
            QMessageBox.warning(self, "Warning", "Please select a project folder first.")
            return False

        return True

    def run_task(self, func, cb=None):
        self._set_state(AppState.TASK_RUNNING)
        self.pbar.setValue(0)

        w = Worker(func)
        # Store reference to prevent GC before signal is processed
        self._active_workers.add(w)

        def done(res):
            # IMPORTANT: The try-finally block guarantees that the state resets to IDLE,
            # even if the callback function (cb) fails with an error.
            try:
                # Cleanup reference
                self._active_workers.discard(w)
                if cb:
                    cb(res)
            except Exception as e:
                logging.error(f"Error in task callback: {e}")
                traceback.print_exc()
                QMessageBox.critical(self, "Callback Error", f"An error occurred after the task finished:\n{e}")
            finally:
                self._set_state(AppState.IDLE)

        def error_handler(title, message):
            self._active_workers.discard(w)
            self._error(title, message)

        w.signals.taskFinished.connect(done)
        w.signals.criticalError.connect(error_handler)

        self.pool.start(w)

    def on_task_done(self, res):
        if res and "summary" in res:
            QMessageBox.information(self, "Done", res["summary"])

    def _clean(self):
        if not self.can_run_task(require_project=True):
            return
        dlg = CleanerDialog(self)
        if dlg.exec():
            opts = dlg.get_options()
            self.run_task(lambda: ProjectCleaner(self.project_root, self.core_signals).run(**opts), self._clean_done)

    def _clean_done(self, res):
        if not res:
            return
        msg = QMessageBox(self)
        msg.setWindowTitle("Cleanup")
        msg.setText(res.get("summary", "Done"))
        if f := res.get("failed_files"):
            msg.setDetailedText("\n".join(f))
        msg.exec()

    def _convert_lc(self):
        if not self.can_run_task(require_project=True):
            return
        msg = "This will irreversibly rename ALL files and folders in the project to lowercase.\n\nARE YOU SURE?"
        if QMessageBox.question(self, "Confirm Conversion", msg) == QMessageBox.StandardButton.Yes:
            self.run_task(lambda: ProjectConverter(self.project_root, self.core_signals).run(), self.on_task_done)

    def _dupes(self):
        if not self.can_run_task(require_project=False):
            return
        dlg = DuplicateFinderDialog(self)
        if self.project_root:
            dlg.target_selector.set_path(self.project_root)

        if dlg.exec():
            ref, tgt = dlg.get_paths()
            self.run_task(lambda: DuplicateFinder(self.core_signals).run(ref, tgt), self.on_task_done)

    def _tod(self):
        if not self.can_run_task(require_project=False):
            return
        dlg = TimeOfDayDialog(self)
        if dlg.exec():
            f = dlg.get_file()
            self.run_task(lambda: TimeOfDayConverter(self.core_signals).run(f), self.on_task_done)

    def _analyze(self):
        if not self.can_run_task(require_project=True):
            return
        self.run_task(lambda: ProjectAnalyzer(self.project_root).run(), self._analyze_done)

    def _analyze_done(self, res):
        if not res:
            return
        prep = defaultdict(str)
        if "extensions_counter" in res:
            for ext, count in res["extensions_counter"].items():
                cat = next((c for c, e in AnalysisReportDialog.EXT_CATEGORIES.items() if ext in e), "Other")
                prep[cat] += f"{ext}: {count}\n"
        AnalysisReportDialog(self, f"Files: {res.get('total_files', 0)}", prep).exec()

    def _validate_textures(self):
        if not self.can_run_task(require_project=True):
            return
        self.run_task(
            lambda: TextureValidator(self.project_root, self.core_signals).run(),
            lambda r: TextureReportDialog(self, r).exec(),
        )

    def _unused(self):
        if not self.can_run_task(require_project=True):
            return
        self.run_task(
            lambda: UnusedAssetFinder(self.project_root, self.core_signals).run(),
            lambda r: UnusedAssetsDialog(self, r).exec(),
        )

    def _missing(self):
        if not self.can_run_task(require_project=True):
            return
        self.run_task(
            lambda: MissingAssetFinder(self.project_root, self.core_signals).run(),
            lambda r: MissingAssetsDialog(self, r).exec(),
        )

    def _pack(self):
        if not self.can_run_task(require_project=False):
            return
        PackerDialog(self).exec()

    def _lua(self):
        if not self.can_run_task(require_project=True):
            return
        LuaToolkitDialog(self).exec()

    # --- Slots ---

    @Slot(str)
    def append_log(self, msg):
        self.log.append(msg)

    @Slot(str, str)
    def _error(self, t, m):
        self._set_state(AppState.IDLE)
        QMessageBox.critical(self, t, m)

    @Slot(int, int)
    def _progress(self, c, t):
        self.pbar.setMaximum(t)
        self.pbar.setValue(c)

    @Slot(int)
    def _toggle_log(self, s):
        logging.getLogger().setLevel(logging.DEBUG if s == Qt.Checked else logging.INFO)

    def closeEvent(self, e):
        if self.watcher_service:
            self.watcher_service.stop()
        self.pool.waitForDone(500)
        e.accept()
