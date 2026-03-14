# app/ui/dialogs/lua_dlg.py
import contextlib
import time
from pathlib import Path

from PySide6.QtCore import Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from app.config import UIConfig
from app.tasks.lua import LuaToolkit


class LuaToolkitDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.main_window = parent
        self.setWindowTitle("Lua Tools")
        self.resize(700, 600)
        self.start_time = 0
        self._init_ui()
        self._check_deps()
        self.main_window.core_signals.progressUpdated.connect(self._update_progress)

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Status Group
        status = QGroupBox("Status")
        status_layout = QHBoxLayout(status)
        self.lbl_luac = QLabel("luac: ...")
        self.lbl_stylua = QLabel("stylua: ...")
        status_layout.addWidget(self.lbl_luac)
        status_layout.addWidget(self.lbl_stylua)
        layout.addWidget(status)

        # Diagnostics Group
        grp_diag = QGroupBox("Diagnostics")
        diag_layout = QVBoxLayout(grp_diag)
        self.btn_diag = QPushButton("Run Diagnostics")
        self.btn_diag.clicked.connect(self._run_diag)
        diag_layout.addWidget(self.btn_diag)

        self.lbl_prog = QLabel("Progress: -")
        diag_layout.addWidget(self.lbl_prog)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["File", "Status", "Msg"])
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        diag_layout.addWidget(self.tree)
        layout.addWidget(grp_diag)

        # Formatter Group
        grp_fmt = QGroupBox("Formatter")
        fmt_layout = QVBoxLayout(grp_fmt)
        self.btn_fmt = QPushButton("Format All")
        self.btn_fmt.clicked.connect(self._run_fmt)
        fmt_layout.addWidget(self.btn_fmt)
        layout.addWidget(grp_fmt)

    def _check_deps(self):
        # Initialize toolkit just to check paths (dummy root)
        t = LuaToolkit(Path("."), None)
        ok_luac = t.luac.is_file()
        ok_stylua = t.stylua.is_file()

        self.lbl_luac.setText(f"luac: {'OK' if ok_luac else 'Missing'}")
        self.lbl_stylua.setText(f"stylua: {'OK' if ok_stylua else 'Missing'}")

        self.btn_diag.setEnabled(ok_luac)
        self.btn_fmt.setEnabled(ok_stylua)

    def _run_diag(self):
        if not self.main_window.can_run_task():
            return

        self.tree.clear()
        self.start_time = time.time()
        self.btn_diag.setEnabled(False)

        self.main_window.run_task(
            lambda: LuaToolkit(self.main_window.project_root, self.main_window.core_signals).run_diagnostics(),
            self._on_diag_done,
        )

    def _run_fmt(self):
        if not self.main_window.can_run_task():
            return

        if QMessageBox.question(self, "Confirm", "Irreversible format?") == QMessageBox.Yes:
            self.main_window.run_task(
                lambda: LuaToolkit(self.main_window.project_root, self.main_window.core_signals).run_formatting({}),
                self.main_window.on_task_done,
            )

    @Slot(int, int)
    def _update_progress(self, c, t):
        if self.isVisible() and not self.btn_diag.isEnabled():
            self.lbl_prog.setText(f"{c}/{t} | Time: {time.time() - self.start_time:.1f}s")

    @Slot(object)
    def _on_diag_done(self, results):
        self.btn_diag.setEnabled(True)
        if not isinstance(results, list):
            return

        for r in results:
            c = UIConfig.COLOR_SUCCESS if r.is_syntax_ok else UIConfig.COLOR_ERROR
            item = QTreeWidgetItem([r.relative_path, r.status, r.message])
            for i in range(3):
                item.setForeground(i, QColor(c))
            self.tree.addTopLevelItem(item)

    def closeEvent(self, e):
        with contextlib.suppress(Exception):
            self.main_window.core_signals.progressUpdated.disconnect(self._update_progress)
        super().closeEvent(e)
