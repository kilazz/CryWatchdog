import logging
from collections import defaultdict
from pathlib import Path

from PySide6.QtCore import Qt, Slot
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
from app.core.task_manager import TaskManager
from app.services.watcher import WatcherOptions, WatcherService, WatcherSettings
from app.tasks.analyzer import ProjectAnalyzer
from app.tasks.cleaner import ProjectCleaner
from app.tasks.converter import ProjectConverter
from app.tasks.duplicates import DuplicateFinder
from app.tasks.finding import MissingAssetFinder, UnusedAssetFinder
from app.tasks.texture_validator import TextureValidator
from app.tasks.tod import TimeOfDayConverter
from app.ui.dialogs.cleaner_dlg import CleanerDialog
from app.ui.dialogs.duplicates_dlg import DuplicateFinderDialog
from app.ui.dialogs.finding_dlg import MissingAssetsDialog, UnusedAssetsDialog
from app.ui.dialogs.lua_dlg import LuaToolkitDialog
from app.ui.dialogs.packer_dlg import PackerDialog
from app.ui.dialogs.reports_dlg import AnalysisReportDialog
from app.ui.dialogs.texture_dlg import TextureReportDialog
from app.ui.dialogs.tod_dlg import TimeOfDayDialog

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CryWatchdog")
        self.setGeometry(100, 100, 1100, 700)
        self.project_root: Path | None = None
        self.watcher_service: WatcherService | None = None
        self.state = AppState.IDLE
        self.core_signals = CoreSignals()
        self.task_manager = TaskManager(self)

        self._init_ui()
        self._connect_core()
        self._set_state(AppState.IDLE)

    def _init_ui(self):
        w = QWidget()
        self.setCentralWidget(w)
        layout = QVBoxLayout(w)

        top = QHBoxLayout()
        self.btn_sel = QPushButton("Select Folder")
        self.btn_proj = QPushButton("Project")
        self.btn_util = QPushButton("Utils")
        self.lbl_status = QLabel("Select a project folder.")

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

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(UIConfig.FONT_MONOSPACE)
        layout.addWidget(self.log)

        self.pbar = QProgressBar()
        self.statusBar().addPermanentWidget(self.pbar)
        self.pbar.hide()

        self.btn_sel.clicked.connect(self._select_folder)
        self.btn_watch.clicked.connect(self._toggle_watch)
        self.opts["show_detailed_log"].stateChanged.connect(self._toggle_log)

    def _connect_core(self):
        self.core_signals.indexingStarted.connect(lambda: self._set_state(AppState.INDEXING))
        self.core_signals.indexingFinished.connect(lambda: self._set_state(AppState.WATCHING))
        self.core_signals.watcherStopped.connect(lambda: self._set_state(AppState.IDLE))
        self.core_signals.criticalError.connect(self._error)
        self.core_signals.progressUpdated.connect(self._progress)
        self.task_manager.stateChanged.connect(self._set_state)

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
            logger.info(f"Selected: {d}")
            self._set_state(AppState.IDLE)

    def _toggle_watch(self):
        if self.state in [AppState.WATCHING, AppState.INDEXING]:
            if self.watcher_service:
                self.watcher_service.stop()
        elif self.project_root is not None:
            opts: WatcherOptions = {
                "match_any_texture_extension": self.opts["match_any_texture_extension"].isChecked(),
                "allow_dir_change": self.opts["allow_dir_change"].isChecked(),
                "dry_run": self.opts["dry_run"].isChecked(),
            }
            settings: WatcherSettings = {
                "project_root": self.project_root,
                "watcher_options": opts,
            }
            self.watcher_service = WatcherService(settings, self.core_signals)
            self.watcher_service.start()

    def can_run_task(self, require_project=True):
        return self.task_manager.can_run_task(self.state, require_project, bool(self.project_root))

    def run_task(self, func, cb=None):
        self.pbar.setValue(0)
        self.task_manager.run_task(func, cb, self._error)

    def on_task_done(self, res):
        if res and "summary" in res:
            QMessageBox.information(self, "Done", res["summary"])

    def _clean(self):
        if not self.can_run_task(require_project=True) or self.project_root is None:
            return
        project_root = self.project_root
        dlg = CleanerDialog(self)
        if dlg.exec():
            opts = dlg.get_options()
            self.run_task(lambda: ProjectCleaner(project_root, self.core_signals).run(**opts), self._clean_done)

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
        if not self.can_run_task(require_project=True) or self.project_root is None:
            return
        project_root = self.project_root
        msg = "This will irreversibly rename ALL files and folders in the project to lowercase.\n\nARE YOU SURE?"
        if QMessageBox.question(self, "Confirm Conversion", msg) == QMessageBox.StandardButton.Yes:
            self.run_task(lambda: ProjectConverter(project_root, self.core_signals).run(), self.on_task_done)

    def _dupes(self):
        if not self.can_run_task(require_project=False):
            return
        dlg = DuplicateFinderDialog(self)
        if self.project_root:
            dlg.target_selector.set_path(self.project_root)

        if dlg.exec():
            ref, tgt = dlg.get_paths()
            if ref and tgt:
                self.run_task(lambda: DuplicateFinder(self.core_signals).run(ref, tgt), self.on_task_done)

    def _tod(self):
        if not self.can_run_task(require_project=False):
            return
        dlg = TimeOfDayDialog(self)
        if dlg.exec():
            f = dlg.get_file()
            if f:
                self.run_task(lambda: TimeOfDayConverter(self.core_signals).run(f), self.on_task_done)

    def _analyze(self):
        if not self.can_run_task(require_project=True) or self.project_root is None:
            return
        project_root = self.project_root
        self.run_task(lambda: ProjectAnalyzer(project_root).run(), self._analyze_done)

    def _analyze_done(self, res):
        if not res:
            return

        prep = defaultdict(dict)

        logger.info("--- [ANALYSIS] Project File Distribution Report ---")
        logger.info(f"Total files scanned: {res.get('total_files', 0)}")
        logger.info(f"Scan duration: {res.get('duration', 0.0):.2f}s")

        if "extensions_counter" in res:
            sorted_extensions = sorted(res["extensions_counter"].items(), key=lambda x: x[1], reverse=True)

            for ext, count in sorted_extensions:
                cat = next((c for c, e in AnalysisReportDialog.EXT_CATEGORIES.items() if ext in e), "Other")
                prep[cat][ext] = count
                logger.info(f"  Extension: {ext:<12} | Count: {count}")

        logger.info("--- [ANALYSIS] End of Report ---")

        dlg = AnalysisReportDialog(
            self,
            f"Total Files Scanned: {res.get('total_files', 0)} (Time: {res.get('duration', 0.0):.2f}s)",
            prep,
        )
        dlg.exec()

    def _validate_textures(self):
        if not self.can_run_task(require_project=True) or self.project_root is None:
            return
        project_root = self.project_root
        self.run_task(
            lambda: TextureValidator(project_root, self.core_signals).run(),
            lambda r: TextureReportDialog(self, r).exec(),
        )

    def _unused(self):
        if not self.can_run_task(require_project=True) or self.project_root is None:
            return
        project_root = self.project_root
        self.run_task(
            lambda: UnusedAssetFinder(project_root, self.core_signals).run(),
            lambda r: UnusedAssetsDialog(self, r).exec(),
        )

    def _missing(self):
        if not self.can_run_task(require_project=True) or self.project_root is None:
            return
        project_root = self.project_root
        self.run_task(
            lambda: MissingAssetFinder(project_root, self.core_signals).run(),
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
        logging.getLogger().setLevel(logging.DEBUG if s == Qt.CheckState.Checked.value else logging.INFO)

    def closeEvent(self, e):
        if self.watcher_service:
            self.watcher_service.stop()
        self.task_manager.wait_for_done(500)
        e.accept()
