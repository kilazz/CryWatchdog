# app/ui_dialogs.py
import contextlib
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import AppConfig, LuaFileAnalysisResult, UIConfig
from app.tasks import AssetPacker, AssetUnpacker, LuaToolkit

# Forward reference for type hint
if False:
    from app.main_window import MainWindow


class PathSelector(QWidget):
    """A composite widget with a button and a line edit for selecting paths."""

    def __init__(self, label_text: str, is_file: bool = False, is_save: bool = False):
        super().__init__()
        self.is_file, self.is_save = is_file, is_save
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.button = QPushButton(label_text)
        self.path_edit = QLineEdit()
        layout.addWidget(self.button)
        layout.addWidget(self.path_edit)
        self.button.clicked.connect(self._select_path)

    def _select_path(self):
        """Opens a file or directory dialog based on the widget's configuration."""
        if self.is_file:
            path, _ = QFileDialog.getOpenFileName(self, "Select File")
        elif self.is_save:
            path, _ = QFileDialog.getSaveFileName(self, "Save File As", filter="Text Files (*.txt)")
        else:
            path = QFileDialog.getExistingDirectory(self, "Select Folder")
        if path:
            self.path_edit.setText(path)

    def get_path(self) -> Path | None:
        """Returns the selected path as a Path object, or None."""
        text = self.path_edit.text()
        return Path(text) if text else None

    def set_path(self, path: Path):
        """Sets the text of the line edit to the given path."""
        self.path_edit.setText(str(path))


class CleanerDialog(QDialog):
    """A dialog for configuring and running the ProjectCleaner task."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Clean & Normalize Assets")
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        self.options_widgets = {}

        # --- Encoding and Line Endings ---
        norm_group = QGroupBox("Encoding & Line Ending Normalization")
        norm_layout = QVBoxLayout(norm_group)
        self.options_widgets["normalize_encoding_check"] = QCheckBox("Enable Normalization")
        self.options_widgets["normalize_encoding_check"].setChecked(True)
        norm_layout.addWidget(self.options_widgets["normalize_encoding_check"])

        enc_box = QHBoxLayout()
        enc_box.addWidget(QLabel("Target Encoding:"))
        self.options_widgets["target_encoding"] = QComboBox()
        self.options_widgets["target_encoding"].addItems(["UTF-8", "UTF-16", "ISO-8859-1"])
        self.options_widgets["target_encoding"].setCurrentText("UTF-8")
        enc_box.addWidget(self.options_widgets["target_encoding"])
        enc_box.addStretch()
        norm_layout.addLayout(enc_box)

        nl_box = QHBoxLayout()
        nl_box.addWidget(QLabel("Line Endings:"))
        self.options_widgets["newline_type"] = QComboBox()
        self.options_widgets["newline_type"].addItems(["CRLF (Windows)", "LF (Unix/macOS)", "CR (Classic Mac OS)"])
        nl_box.addWidget(self.options_widgets["newline_type"])
        nl_box.addStretch()
        norm_layout.addLayout(nl_box)
        layout.addWidget(norm_group)

        # --- Other General Options ---
        self.options_widgets["strip_bom"] = QCheckBox(
            "Strip non-text file headers (e.g., from XMLs saved in some editors)"
        )
        self.options_widgets["strip_bom"].setChecked(True)
        layout.addWidget(self.options_widgets["strip_bom"])

        self.options_widgets["trim_whitespace"] = QCheckBox("Trim Trailing Whitespace from lines")
        self.options_widgets["trim_whitespace"].setChecked(True)
        layout.addWidget(self.options_widgets["trim_whitespace"])

        # --- Path Cleaning Options ---
        path_group = QGroupBox("Path Cleaning Options")
        path_layout = QVBoxLayout(path_group)
        self.options_widgets["normalize_paths"] = QCheckBox("Normalize path separators to forward slashes ( / )")
        self.options_widgets["normalize_paths"].setChecked(True)
        path_layout.addWidget(self.options_widgets["normalize_paths"])
        self.options_widgets["resolve_redundant_paths"] = QCheckBox(
            "Resolve redundant paths (e.g., 'folder/../file' -> 'file')"
        )
        self.options_widgets["resolve_redundant_paths"].setChecked(True)
        path_layout.addWidget(self.options_widgets["resolve_redundant_paths"])
        self.options_widgets["convert_to_lowercase"] = QCheckBox("Convert asset paths inside files to lowercase")
        self.options_widgets["convert_to_lowercase"].setChecked(True)
        path_layout.addWidget(self.options_widgets["convert_to_lowercase"])
        layout.addWidget(path_group)

        # --- Warning and Buttons ---
        warning = QLabel("WARNING: This is an irreversible operation. Please ensure you have a backup.")
        warning.setStyleSheet(f"color: {UIConfig.COLOR_ERROR};")
        layout.addWidget(warning, 0, Qt.AlignmentFlag.AlignCenter)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_options(self) -> dict:
        """Returns a dictionary of the selected cleaning options."""
        params = {
            k: v.isChecked() if isinstance(v, QCheckBox) else v.currentText() for k, v in self.options_widgets.items()
        }
        params["normalize_encoding"] = params.pop("normalize_encoding_check")
        params["newline_type_label"] = params.pop("newline_type")
        return params


class AnalysisReportDialog(QDialog):
    """A dialog to display the project analysis report."""

    EXT_CATEGORIES = {
        "Textures": {".dds", ".tif", ".tiff", ".png", ".jpg", ".jpeg", ".tga", ".bmp", ".gif", ".hdr", ".exr", ".gfx"},
        "Models": {".cgf", ".cga", ".chr", ".skin", ".fbx", ".obj", ".3ds"},
        "Scripts & Configs": {".lua", ".mtl", ".xml", ".lyr", ".lay", ".cdf", ".json", ".cfg", ".ini"},
        "Archives": {".pak", ".zip", ".rar", ".7z", ".dat", ".bak"},
        "Audio": {".wav", ".ogg", ".mp3"},
        "Other Files": {},
    }

    def __init__(self, parent, header_text: str, prepared_data: dict[str, str]):
        super().__init__(parent)
        self.setWindowTitle("Analysis Report")
        self.setGeometry(100, 100, 1400, 800)
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(QLabel(header_text))
        columns_layout = QHBoxLayout()
        main_layout.addLayout(columns_layout)

        for category_name in self.EXT_CATEGORIES:
            if content := prepared_data.get(category_name):
                col_layout = QVBoxLayout()
                title = QLabel(f"--- {category_name} ---")
                title.setFont(UIConfig.FONT_MONOSPACE)
                col_layout.addWidget(title)
                content_label = QLabel(content)
                content_label.setFont(UIConfig.FONT_MONOSPACE)
                content_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                col_layout.addWidget(content_label)
                col_layout.addStretch()
                columns_layout.addLayout(col_layout)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)


class PackerDialog(QDialog):
    """A dialog for the AssetPacker and AssetUnpacker tools."""

    def __init__(self, parent: "MainWindow"):
        super().__init__(parent)
        self.main_window = parent
        self.setWindowTitle("Text Packer Tool")
        self.setMinimumWidth(600)
        layout = QVBoxLayout(self)

        pack_group = QGroupBox("Pack Files")
        pack_layout = QVBoxLayout(pack_group)
        self.pack_source_selector = PathSelector("Source Folder...")
        self.pack_output_selector = PathSelector("Output File...", is_save=True)
        self.pack_ext_edit = QLineEdit(".lua, .xml, .txt, .cfg")
        pack_layout.addWidget(self.pack_source_selector)
        pack_layout.addWidget(self.pack_output_selector)
        pack_layout.addWidget(QLabel("Extensions (comma-separated):"))
        pack_layout.addWidget(self.pack_ext_edit)
        self.pack_button = QPushButton("Pack Files")
        pack_layout.addWidget(self.pack_button)
        layout.addWidget(pack_group)

        unpack_group = QGroupBox("Unpack File")
        unpack_layout = QVBoxLayout(unpack_group)
        self.unpack_source_selector = PathSelector("Archive File...", is_file=True)
        self.unpack_output_selector = PathSelector("Output Folder...")
        self.unpack_button = QPushButton("Unpack File")
        unpack_layout.addWidget(self.unpack_source_selector)
        unpack_layout.addWidget(self.unpack_output_selector)
        unpack_layout.addWidget(self.unpack_button)
        layout.addWidget(unpack_group)

        if self.main_window.project_root:
            self.pack_source_selector.set_path(self.main_window.project_root)
            self.unpack_output_selector.set_path(self.main_window.project_root)

        self.pack_button.clicked.connect(self._run_packing)
        self.unpack_button.clicked.connect(self._run_unpacking)

    def _run_packing(self):
        source = self.pack_source_selector.get_path()
        output = self.pack_output_selector.get_path()
        exts_str = self.pack_ext_edit.text()
        if not (source and output and exts_str):
            QMessageBox.warning(self, "Input Missing", "Please provide a source folder, output file, and extensions.")
            return
        extensions = tuple(ext.strip().lower() for ext in exts_str.split(","))

        def task():
            return AssetPacker(source, output, extensions, self.main_window.core_signals).run()

        self.main_window.run_task_in_thread(task, on_complete=self.main_window.on_simple_task_complete)
        self.accept()

    def _run_unpacking(self):
        source = self.unpack_source_selector.get_path()
        output = self.unpack_output_selector.get_path()
        if not (source and source.is_file() and output):
            QMessageBox.warning(self, "Input Missing", "Please provide a valid archive file and an output folder.")
            return

        msg = f"This will restore files into:\n{output.resolve()}\n\nExisting files will be OVERWRITTEN. Continue?"
        if QMessageBox.question(self, "Confirm Unpack", msg) == QMessageBox.StandardButton.Yes:

            def task():
                return AssetUnpacker(source, output, self.main_window.core_signals).run()

            self.main_window.run_task_in_thread(task, on_complete=self.main_window.on_simple_task_complete)
            self.accept()


class LuaToolkitDialog(QDialog):
    """Dialog for Lua diagnostics and formatting tools."""

    def __init__(self, parent: "MainWindow"):
        super().__init__(parent)
        self.main_window = parent
        self.setWindowTitle("Lua Tools")
        self.setMinimumSize(700, 600)
        self.diag_start_time = 0
        self._setup_ui()
        self._check_dependencies()
        self._connect_signals()

    def _setup_ui(self):
        """Builds the UI components of the dialog."""
        layout = QVBoxLayout(self)

        status_group = QGroupBox("Tool Status")
        status_layout = QHBoxLayout(status_group)
        self.luac_status_label = QLabel("luac: Checking...")
        self.stylua_status_label = QLabel("stylua: Checking...")
        status_layout.addWidget(self.luac_status_label)
        status_layout.addWidget(self.stylua_status_label)
        layout.addWidget(status_group)

        diag_group = QGroupBox("Syntax & Encoding Diagnoser")
        diag_layout = QVBoxLayout(diag_group)
        self.lua_diag_button = QPushButton("Run Diagnostics")
        diag_layout.addWidget(self.lua_diag_button)
        summary_group = QGroupBox("Summary")
        summary_layout = QHBoxLayout(summary_group)
        self.diag_progress_label = QLabel("Progress: N/A")
        self.diag_errors_label = QLabel("Issues Found: N/A")
        self.diag_time_label = QLabel("Time: N/A")
        summary_layout.addWidget(self.diag_progress_label)
        summary_layout.addWidget(self.diag_errors_label)
        summary_layout.addWidget(self.diag_time_label)
        diag_layout.addWidget(summary_group)
        self.lua_results_tree = QTreeWidget()
        self.lua_results_tree.setHeaderLabels(["File", "Status", "Details", "Encoding"])
        self.lua_results_tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        diag_layout.addWidget(self.lua_results_tree)
        layout.addWidget(diag_group)

        format_group = QGroupBox("Code Formatter (StyLua)")
        format_layout = QVBoxLayout(format_group)
        self.stylua_vars = {
            "column_width": QLineEdit("120"),
            "indent_type": QComboBox(),
            "indent_width": QLineEdit("4"),
            "quote_style": QComboBox(),
        }
        self.stylua_vars["indent_type"].addItems(["Spaces", "Tabs"])
        self.stylua_vars["quote_style"].addItems(["AutoPreferSingle", "AutoPreferDouble", "ForceSingle", "ForceDouble"])
        format_layout.addWidget(QLabel("Column Width:"))
        format_layout.addWidget(self.stylua_vars["column_width"])
        format_layout.addWidget(QLabel("Indent Type:"))
        format_layout.addWidget(self.stylua_vars["indent_type"])
        format_layout.addWidget(QLabel("Indent Width:"))
        format_layout.addWidget(self.stylua_vars["indent_width"])
        format_layout.addWidget(QLabel("Quote Style:"))
        format_layout.addWidget(self.stylua_vars["quote_style"])
        self.lua_format_button = QPushButton("Format All .lua Files")
        format_layout.addWidget(self.lua_format_button)
        layout.addWidget(format_group)

    def _connect_signals(self):
        """Connects widget signals to their corresponding slots."""
        self.lua_diag_button.clicked.connect(self._run_lua_diagnostics)
        self.lua_format_button.clicked.connect(self._run_lua_formatting)
        self.main_window.core_signals.progressUpdated.connect(self.update_diag_progress)

    def _check_dependencies(self):
        """Checks for luac.exe and stylua.exe and updates the UI."""
        script_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
        luac_path = script_dir / AppConfig.LUA_COMPILER_EXE_NAME
        stylua_path = script_dir / AppConfig.STYLUO_EXE_NAME

        if luac_path.is_file():
            self.luac_status_label.setText("luac: Available")
            self.luac_status_label.setStyleSheet(f"color: {UIConfig.COLOR_SUCCESS};")
            self.lua_diag_button.setEnabled(True)
        else:
            self.luac_status_label.setText("luac: Not Found")
            self.luac_status_label.setStyleSheet(f"color: {UIConfig.COLOR_ERROR};")
            self.lua_diag_button.setEnabled(False)

        if stylua_path.is_file():
            self.stylua_status_label.setText("stylua: Available")
            self.stylua_status_label.setStyleSheet(f"color: {UIConfig.COLOR_SUCCESS};")
            self.lua_format_button.setEnabled(True)
        else:
            self.stylua_status_label.setText("stylua: Not Found")
            self.stylua_status_label.setStyleSheet(f"color: {UIConfig.COLOR_ERROR};")
            self.lua_format_button.setEnabled(False)

    def _set_buttons_enabled(self, enabled: bool):
        """Helper to enable/disable dialog buttons based on tool availability."""
        can_diag = "Available" in self.luac_status_label.text()
        can_format = "Available" in self.stylua_status_label.text()
        self.lua_diag_button.setEnabled(enabled and can_diag)
        self.lua_format_button.setEnabled(enabled and can_format)

    def _run_lua_diagnostics(self):
        """Starts the Lua diagnostics task."""
        if not self.main_window.can_run_task():
            return

        self._set_buttons_enabled(False)
        self.lua_results_tree.clear()
        self.diag_start_time = time.time()

        def task():
            return LuaToolkit(self.main_window.project_root, self.main_window.core_signals).run_diagnostics()

        self.main_window.run_task_in_thread(task, on_complete=self.on_diagnostics_complete)

    def _run_lua_formatting(self):
        """Starts the Lua formatting task."""
        if not self.main_window.can_run_task():
            return

        msg = "This will irreversibly modify all .lua files in the project. Do you have a backup?"
        if QMessageBox.question(self, "Confirm Format", msg) == QMessageBox.StandardButton.Yes:
            self._set_buttons_enabled(False)
            config = {k: v.text() if isinstance(v, QLineEdit) else v.currentText() for k, v in self.stylua_vars.items()}

            def task():
                return LuaToolkit(self.main_window.project_root, self.main_window.core_signals).run_formatting(config)

            self.main_window.run_task_in_thread(task, on_complete=self.on_formatting_complete)

    @Slot(int, int)
    def update_diag_progress(self, current: int, total: int):
        """Updates the progress labels during the diagnostics task."""
        if self.isVisible() and not self.lua_diag_button.isEnabled():
            self.diag_progress_label.setText(f"Progress: {current}/{total}")
            elapsed = time.time() - self.diag_start_time
            self.diag_time_label.setText(f"Time: {elapsed:.2f}s")
            self.diag_errors_label.setText(f"Issues Found: {self.lua_results_tree.topLevelItemCount()}")

    @Slot(object)
    def on_diagnostics_complete(self, results: list[LuaFileAnalysisResult]):
        """Handles the completion of the diagnostics task."""
        if not self.isVisible():
            return

        if isinstance(results, list):
            duration = time.time() - self.diag_start_time
            self.diag_time_label.setText(f"Time: {duration:.2f}s")

            status_map = {
                "ok": ("✅", UIConfig.COLOR_SUCCESS),
                "syntax_error": ("❌", UIConfig.COLOR_ERROR),
                "encoding_issue": ("⚠️", UIConfig.COLOR_WARNING),
                "path_error": ("📁", UIConfig.COLOR_ERROR),
            }
            for r in results:
                # FIXED: Order swapped to define variables before use
                icon, color_name = status_map.get(r.status, ("", "white"))
                item = QTreeWidgetItem(
                    [str(r.relative_path), f"{icon} {r.status.replace('_', ' ').title()}", r.message, r.encoding]
                )
                for i in range(item.columnCount()):
                    item.setForeground(i, QColor(color_name))
                self.lua_results_tree.addTopLevelItem(item)

            self.diag_errors_label.setText(f"Issues Found: {self.lua_results_tree.topLevelItemCount()}")
            if not results:
                QMessageBox.information(self, "Diagnostics Complete", "No issues found.")

        self._set_buttons_enabled(True)

    @Slot(object)
    def on_formatting_complete(self, results: dict | None):
        """Callback for the formatting task."""
        if self.isVisible():
            self.main_window.on_simple_task_complete(results)
            self._set_buttons_enabled(True)

    def closeEvent(self, event):
        """Disconnects signals to prevent memory leaks."""
        with contextlib.suppress(TypeError, RuntimeError):
            self.main_window.core_signals.progressUpdated.disconnect(self.update_diag_progress)
        super().closeEvent(event)
