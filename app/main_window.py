# app/main_window.py
import logging
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool, Slot
from PySide6.QtGui import QIntValidator
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

from app.config import AppConfig, AppState, UIConfig
from app.tasks import (
    MissingAssetFinder,
    ProjectAnalyzer,
    ProjectCleaner,
    ProjectConverter,
    UnusedAssetFinder,
)
from app.ui_dialogs import (
    AnalysisReportDialog,
    CleanerDialog,
    LuaToolkitDialog,
    MissingAssetsDialog,
    PackerDialog,
    UnusedAssetsDialog,
)
from app.utils import CoreSignals, Worker
from app.watcher import WatcherService


class MainWindow(QMainWindow):
    """The main application window."""

    def __init__(self):
        super().__init__()
        self._int_validator = QIntValidator(1, 1000, self)
        self.project_root: Path | None = None
        self.watcher_service: WatcherService | None = None
        self.state = AppState.IDLE
        self.thread_pool = QThreadPool()
        self.core_signals = CoreSignals()
        self.script_dir = Path(__file__).resolve().parent

        self._setup_window()
        self._setup_ui()
        self._connect_signals()

        # Initialize with default debug state
        self._toggle_debug_log(self.watcher_options.get("show_detailed_log").checkState())
        self._set_state(AppState.IDLE)

    def _setup_window(self):
        """Initializes main window properties."""
        self.setWindowTitle("AssetWatchdog")
        self.setGeometry(100, 100, 1100, 700)

    def get_int_validator(self):
        """Exposes the integer validator for sub-dialogs."""
        return QIntValidator(self._int_validator.bottom(), self._int_validator.top(), self)

    def _setup_ui(self):
        """Constructs the UI of the main window."""
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        main_layout.addLayout(self._create_top_bar())
        main_layout.addWidget(self._create_watcher_group())
        main_layout.addWidget(self._create_log_view())

        self.progress_bar = QProgressBar(self)
        self.statusBar().addPermanentWidget(self.progress_bar)
        self.progress_bar.hide()

    def _create_top_bar(self) -> QHBoxLayout:
        """Creates the top bar with menus, project selection, and status label."""
        top_bar_layout = QHBoxLayout()
        top_bar_layout.setContentsMargins(5, 5, 5, 5)
        top_bar_layout.setSpacing(10)

        # --- Menus ---
        self.project_tools_button = QPushButton("Project")
        self.project_tools_button.setMinimumWidth(90)

        project_tools_menu = QMenu(self)
        self.analyze_action = project_tools_menu.addAction("Analyze Project Files...")
        self.unused_action = project_tools_menu.addAction("Find Unused Assets (Scavenger)...")
        self.missing_action = project_tools_menu.addAction("Check for Missing Textures/Assets...")
        project_tools_menu.addSeparator()
        self.lua_action = project_tools_menu.addAction("Lua Tools...")
        self.clean_action = project_tools_menu.addAction("Clean & Normalize Assets...")
        project_tools_menu.addSeparator()
        self.lc_action = project_tools_menu.addAction("Convert Filenames to Lowercase...")

        self.project_tools_button.setMenu(project_tools_menu)

        self.utilities_button = QPushButton("Utils")
        self.utilities_button.setMinimumWidth(90)
        utilities_menu = QMenu(self)
        self.packer_action = utilities_menu.addAction("Text Packer Tool...")
        self.utilities_button.setMenu(utilities_menu)

        # --- Action Button ---
        self.select_button = QPushButton("Select Folder")
        self.select_button.setMinimumWidth(110)
        self.status_label = QLabel("Select a project folder to begin.")

        # --- Layout Assembly ---
        top_bar_layout.addWidget(self.select_button)
        top_bar_layout.addWidget(self.project_tools_button)
        top_bar_layout.addWidget(self.utilities_button)
        top_bar_layout.addStretch(1)
        top_bar_layout.addWidget(self.status_label)
        return top_bar_layout

    def _create_watcher_group(self) -> QGroupBox:
        """Creates the GroupBox containing the watchdog controls."""
        watcher_group = QGroupBox("Real-time Asset Watchdog")
        watcher_layout = QVBoxLayout(watcher_group)
        options_layout = QHBoxLayout()

        self.watcher_options = {}
        opts = [
            ("match_any_texture_extension", "Match Any Texture Extension (tif/dds)", True),
            ("allow_ext_change", "Patch on Extension Changes", True),
            ("allow_dir_change", "Patch on Directory Renames", True),
            ("dry_run", "Dry Run (Simulation Mode - No Writes)", False),
            ("show_detailed_log", "Enable Debug Log (Python)", False),
        ]
        for name, text, default in opts:
            self.watcher_options[name] = QCheckBox(text)
            self.watcher_options[name].setChecked(default)

            # Highlight Dry Run to make it obvious
            if name == "dry_run":
                self.watcher_options[name].setStyleSheet(f"color: {UIConfig.COLOR_DRY_RUN}; font-weight: bold;")

            options_layout.addWidget(self.watcher_options[name])

        self.toggle_button = QPushButton("Start Watchdog")
        watcher_layout.addLayout(options_layout)
        watcher_layout.addWidget(self.toggle_button)
        return watcher_group

    def _create_log_view(self) -> QTextEdit:
        """Creates the text edit widget for logging."""
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(UIConfig.FONT_MONOSPACE)
        self.log_text.document().setMaximumBlockCount(AppConfig.LOG_MAX_BLOCK_COUNT)
        return self.log_text

    def _connect_signals(self):
        """Connects all signals for the application."""
        self.select_button.clicked.connect(self._select_folder)
        self.toggle_button.clicked.connect(self._toggle_watching)

        # Actions
        self.clean_action.triggered.connect(self._open_cleaner_dialog)
        self.analyze_action.triggered.connect(self._analyze_project)
        self.unused_action.triggered.connect(self._run_unused_finder)
        self.missing_action.triggered.connect(self._run_missing_finder)
        self.lc_action.triggered.connect(self._run_lc_conversion)
        self.packer_action.triggered.connect(self._open_packer_dialog)
        self.lua_action.triggered.connect(self._open_lua_dialog)

        self.watcher_options["show_detailed_log"].stateChanged.connect(self._toggle_debug_log)

        # Core signals
        self.core_signals.indexingStarted.connect(lambda: self._set_state(AppState.INDEXING))
        self.core_signals.indexingFinished.connect(lambda: self._set_state(AppState.WATCHING))
        self.core_signals.watcherStopped.connect(lambda: self._set_state(AppState.IDLE))
        self.core_signals.criticalError.connect(self.show_critical_error)
        self.core_signals.progressUpdated.connect(self.update_progress)

    @Slot(int)
    def _toggle_debug_log(self, state: int):
        """Changes the Python logging level based on the checkbox state."""
        is_checked = state == Qt.CheckState.Checked.value
        if is_checked:
            logging.getLogger().setLevel(logging.DEBUG)
            logging.info("Python Debug Log Enabled. Logging level set to DEBUG.")
        else:
            if logging.getLogger().level != logging.INFO:
                logging.info("Python Debug Log Disabled. Logging level set to INFO.")
            logging.getLogger().setLevel(logging.INFO)

    def _set_state(self, new_state: AppState):
        """Updates the UI to reflect the current application state."""
        self.state = new_state
        has_project = bool(self.project_root)
        is_idle = new_state == AppState.IDLE
        is_watching = new_state == AppState.WATCHING
        project_name = self.project_root.name if has_project else "No project selected"

        states = {
            AppState.IDLE: ("Start Watchdog", f".../{project_name}", UIConfig.COLOR_IDLE),
            AppState.INDEXING: ("Stop Watchdog", "Status: Indexing...", UIConfig.COLOR_SUCCESS),
            AppState.WATCHING: ("Stop Watchdog", "Status: ● Watching...", UIConfig.COLOR_INFO),
            AppState.STOPPING: ("Stopping...", "Status: Stopping...", UIConfig.COLOR_WARNING),
            AppState.TASK_RUNNING: ("Running Task...", "Status: Running task...", UIConfig.COLOR_WARNING),
        }
        btn_text, status_text, color = states.get(new_state, ("ERROR", "ERROR", UIConfig.COLOR_ERROR))

        self.toggle_button.setText(btn_text)
        self.status_label.setText(status_text)
        self.status_label.setStyleSheet(f"color: {color};")

        self.select_button.setEnabled(is_idle)
        self.project_tools_button.setEnabled(is_idle and has_project)
        self.utilities_button.setEnabled(is_idle)
        self.toggle_button.setEnabled((is_idle and has_project) or is_watching or new_state == AppState.INDEXING)

        opts_enabled = is_idle or is_watching
        for widget in self.watcher_options.values():
            widget.setEnabled(opts_enabled)

        if new_state not in [AppState.TASK_RUNNING, AppState.INDEXING]:
            self.progress_bar.hide()
        else:
            self.progress_bar.show()

    def _cleanup_temp_files(self):
        """Removes any orphaned .tmp files from previous sessions."""
        if not self.project_root:
            return
        count = 0
        try:
            for p in self.project_root.rglob("*.tmp"):
                p.unlink()
                count += 1
            if count > 0:
                logging.info(f"Removed {count} orphaned temporary file(s).")
        except Exception as e:
            logging.warning(f"Could not clean up temporary files: {e}")

    def _select_folder(self):
        """Opens a dialog to select the root project folder."""
        start_dir = str(self.project_root) if self.project_root else str(self.script_dir)
        folder = QFileDialog.getExistingDirectory(self, "Select Project Root", dir=start_dir)
        if folder:
            self.project_root = Path(folder)
            logging.info(f"Project folder selected: {folder}")
            self._set_state(AppState.IDLE)
            self._cleanup_temp_files()

    def _toggle_watching(self):
        """Starts or stops the watchdog service."""
        if self.state in [AppState.INDEXING, AppState.WATCHING]:
            self._stop_watching()
        elif self.state == AppState.IDLE and self.project_root:
            self._start_watching()

    def _start_watching(self):
        """Configures and starts the WatcherService."""
        if not self.project_root:
            return
        opts = {name: widget.isChecked() for name, widget in self.watcher_options.items()}

        if opts.get("dry_run"):
            logging.warning("Watchdog starting in DRY RUN mode. No files will be modified.")

        service_settings = {"project_root": self.project_root, "watcher_options": opts}
        self.watcher_service = WatcherService(service_settings, self.core_signals)
        self.watcher_service.start()

    def _stop_watching(self):
        """Stops the WatcherService if it is running."""
        if self.watcher_service and self.watcher_service.is_alive():
            self._set_state(AppState.STOPPING)
            self.watcher_service.stop()

    def _open_cleaner_dialog(self):
        """Opens the cleaner dialog and runs the task if confirmed."""
        if not self.can_run_task():
            return
        dialog = CleanerDialog(self)
        if dialog.exec():
            opts = dialog.get_options()

            def task():
                return ProjectCleaner(self.project_root, self.core_signals).run(**opts)

            self.run_task_in_thread(task, on_complete=self.on_cleanup_complete)

    def _analyze_project(self):
        """Runs the project analysis task."""
        if self.can_run_task():

            def task():
                return ProjectAnalyzer(self.project_root).run()

            self.run_task_in_thread(task, on_complete=self.on_analysis_complete)

    def _run_unused_finder(self):
        """Runs the unused asset scanner task."""
        if self.can_run_task():

            def task():
                return UnusedAssetFinder(self.project_root, self.core_signals).run()

            self.run_task_in_thread(task, on_complete=self.on_unused_scan_complete)

    def _run_missing_finder(self):
        """Runs the missing asset/broken reference scanner."""
        if self.can_run_task():

            def task():
                return MissingAssetFinder(self.project_root, self.core_signals).run()

            self.run_task_in_thread(task, on_complete=self.on_missing_scan_complete)

    def _open_packer_dialog(self):
        """Opens the packer/unpacker tool dialog."""
        if self.can_run_task(silent=True):
            PackerDialog(self).exec()

    def _open_lua_dialog(self):
        """Opens the Lua toolkit dialog."""
        if self.can_run_task(silent=True):
            LuaToolkitDialog(self).exec()

    def _run_lc_conversion(self):
        """Runs the filename-to-lowercase conversion task."""
        if not self.can_run_task():
            return
        msg = "This will irreversibly rename ALL files and folders in the project to lowercase.\n\nARE YOU SURE?"
        if QMessageBox.question(self, "Confirm Conversion", msg) == QMessageBox.StandardButton.Yes:

            def task():
                return ProjectConverter(self.project_root, self.core_signals).run()

            self.run_task_in_thread(task, on_complete=self.on_simple_task_complete)

    def run_task_in_thread(self, task: Callable, on_complete: Callable | None = None):
        """Executes a given function in a background thread using the QThreadPool."""
        self._set_state(AppState.TASK_RUNNING)
        self.progress_bar.setValue(0)
        worker = Worker(task)

        def on_task_wrapper(result):
            if on_complete:
                on_complete(result)
            try:
                worker.signals.taskFinished.disconnect(on_task_wrapper)
                worker.signals.criticalError.disconnect()
            except (TypeError, RuntimeError):
                pass
            if self.state == AppState.TASK_RUNNING:
                self._set_state(AppState.IDLE)

        worker.signals.taskFinished.connect(on_task_wrapper)
        worker.signals.criticalError.connect(self.show_critical_error)
        worker.signals.criticalError.connect(lambda: self._set_state(AppState.IDLE))
        self.thread_pool.start(worker)

    @Slot(object)
    def on_simple_task_complete(self, results: dict | None):
        """A generic callback for tasks that return a simple summary message."""
        if results and (summary := results.get("summary")):
            QMessageBox.information(self, "Task Complete", summary)

    @Slot(object)
    def on_cleanup_complete(self, results: dict | None):
        """Callback for the cleaner task, which may show detailed error info."""
        if not results:
            return
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Cleanup Complete")
        msg_box.setText(results.get("summary", "Task finished."))
        if failed := results.get("failed_files", []):
            msg_box.setDetailedText("Failed files:\n\n" + "\n".join(failed))
            msg_box.setIcon(QMessageBox.Icon.Warning)
        else:
            msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.exec()

    @Slot(object)
    def on_analysis_complete(self, results: dict | None):
        """Callback for the analysis task, which formats and shows the report dialog."""
        if not results:
            return
        header = f"Analysis Complete | Files: {results['total_files']:,} | Time: {results['duration']:.2f}s"
        categorized: dict[str, list] = defaultdict(list)
        for ext, count in sorted(results["extensions_counter"].items(), key=lambda i: i[1], reverse=True):
            cat = next((c for c, e in AnalysisReportDialog.EXT_CATEGORIES.items() if ext in e), "Other Files")
            categorized[cat].append((ext, count))

        prepared = {}
        category_order = list(AnalysisReportDialog.EXT_CATEGORIES.keys())
        for cat_name in category_order:
            if items := categorized.get(cat_name):
                max_ext = max(len(e) for e, _ in items) if items else 0
                max_count = max(len(f"{c:,}") for _, c in items) if items else 0
                prepared[cat_name] = "\n".join([f"{e:<{max_ext}} : {f'{c:,}':>{max_count}} file(s)" for e, c in items])
        AnalysisReportDialog(self, header, prepared).exec()

    @Slot(object)
    def on_unused_scan_complete(self, results: dict | None):
        """Callback for the unused asset finder task."""
        if results:
            UnusedAssetsDialog(self, results).exec()

    @Slot(object)
    def on_missing_scan_complete(self, results: dict | None):
        """Callback for the missing asset finder task."""
        if results:
            MissingAssetsDialog(self, results).exec()

    def can_run_task(self, silent: bool = False) -> bool:
        """Checks if the application is in a state that allows a new task to run."""
        if self.state != AppState.IDLE:
            if not silent:
                QMessageBox.warning(self, "Warning", "Another operation is already in progress.")
            return False
        if not self.project_root and not silent:
            QMessageBox.warning(self, "Warning", "Please select a project folder first.")
            return False
        return True

    @Slot(str)
    def append_log(self, message: str):
        """Appends a message to the log view."""
        self.log_text.append(message)

    @Slot(str, str)
    def show_critical_error(self, title: str, message: str):
        """Displays a critical error message box."""
        self._set_state(AppState.IDLE)
        QMessageBox.critical(self, title, message)

    @Slot(int, int)
    def update_progress(self, current: int, total: int):
        """Updates the progress bar in the status bar."""
        if total > 0:
            if self.progress_bar.maximum() != total:
                self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)

    def closeEvent(self, event):
        """Handles the window close event, ensuring tasks are stopped gracefully."""
        if self.state in [AppState.TASK_RUNNING, AppState.INDEXING, AppState.STOPPING]:
            reply = QMessageBox.question(
                self,
                "Confirm Exit",
                "A task is running. Are you sure you want to quit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
        if self.watcher_service and self.watcher_service.is_alive():
            self._stop_watching()
        self.thread_pool.waitForDone(1000)
        event.accept()
