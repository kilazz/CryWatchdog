import logging
from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CardWidget,
    CheckBox,
    InfoBar,
    InfoBarPosition,
    ProgressBar,
    PushButton,
    TextEdit,
)

from app.config import AppState, UIConfig
from app.controllers.project_controller import ProjectController
from app.core.signals import CoreSignals
from app.core.task_manager import TaskManager
from app.services.watcher import WatcherOptions, WatcherService, WatcherSettings

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
        self.controller = ProjectController(self)

        self._init_ui()
        self._connect_core()
        self._set_state(AppState.IDLE)

    def _init_ui(self):
        w = QWidget()
        self.setCentralWidget(w)
        layout = QVBoxLayout(w)

        top = QHBoxLayout()
        self.btn_sel = PushButton("Select Folder")
        self.btn_proj = PushButton("Project")
        self.btn_util = PushButton("Utils")
        self.lbl_status = QLabel("Select a project folder.")

        m_proj = QMenu(self)
        m_proj.addAction("Analyze...").triggered.connect(self.controller.analyze_project)
        m_proj.addAction("Validate Textures...").triggered.connect(self.controller.validate_textures)
        m_proj.addSeparator()
        m_proj.addAction("Find Unused...").triggered.connect(self.controller.find_unused)
        m_proj.addAction("Find Missing...").triggered.connect(self.controller.find_missing)
        m_proj.addSeparator()
        m_proj.addAction("Lua Tools...").triggered.connect(self.controller.open_lua_toolkit)
        m_proj.addAction("Clean Assets...").triggered.connect(self.controller.clean_assets)
        m_proj.addSeparator()
        m_proj.addAction("To Lowercase...").triggered.connect(self.controller.convert_lowercase)
        self.btn_proj.setMenu(m_proj)

        m_util = QMenu(self)
        m_util.addAction("Packer...").triggered.connect(self.controller.open_packer)
        m_util.addSeparator()
        m_util.addAction("Duplicate Finder...").triggered.connect(self.controller.find_duplicates)
        m_util.addAction("TOD Converter...").triggered.connect(self.controller.convert_tod)
        self.btn_util.setMenu(m_util)

        top.addWidget(self.btn_sel)
        top.addWidget(self.btn_proj)
        top.addWidget(self.btn_util)
        top.addStretch()
        top.addWidget(self.lbl_status)
        layout.addLayout(top)

        grp = CardWidget()
        gl = QVBoxLayout(grp)
        ol = QHBoxLayout()
        self.opts = {}
        for k, t, d in [
            ("match_any_texture_extension", "Match Any Texture", True),
            ("allow_dir_change", "Patch Dir Moves", True),
            ("dry_run", "Dry Run", False),
            ("show_detailed_log", "Debug Log", False),
        ]:
            cb = CheckBox(t)
            cb.setChecked(d)
            if k == "dry_run":
                cb.setStyleSheet(f"color: {UIConfig.COLOR_DRY_RUN}; font-weight: bold;")
            self.opts[k] = cb
            ol.addWidget(cb)
        self.btn_watch = PushButton("Start Watchdog")
        gl.addLayout(ol)
        gl.addWidget(self.btn_watch)
        layout.addWidget(grp)

        self.log = TextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(UIConfig.FONT_MONOSPACE)
        layout.addWidget(self.log)

        self.pbar = ProgressBar()
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
            InfoBar.success("Project Selected", f"Path: {d}", position=InfoBarPosition.TOP_RIGHT, parent=self)
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

    @Slot(str)
    def append_log(self, msg):
        self.log.append(msg)

    @Slot(str, str)
    def _error(self, t, m):
        self._set_state(AppState.IDLE)
        InfoBar.error(t, m, position=InfoBarPosition.TOP_RIGHT, parent=self)

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
