# app/ui/dialogs/duplicates_dlg.py
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QVBoxLayout,
)

from app.config import UIConfig
from app.ui.widgets import PathSelector


class DuplicateFinderDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Deep Duplicate Finder (Recursive)")
        self.setMinimumWidth(600)
        layout = QVBoxLayout(self)

        info = QLabel(
            "This tool finds files in the TARGET folder that are exact duplicates\n"
            "(content + name) of files in the REFERENCE folder.\n\n"
            "Duplicates will be DELETED from the TARGET folder."
        )
        info.setStyleSheet(f"color: {UIConfig.COLOR_WARNING}; font-weight: bold;")
        layout.addWidget(info)

        self.ref_selector = PathSelector("Select Reference Folder (Keep Files)")
        self.target_selector = PathSelector("Select Target Folder (Delete Dups)")

        layout.addWidget(self.ref_selector)
        layout.addWidget(self.target_selector)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self._validate_and_accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _validate_and_accept(self):
        p1 = self.ref_selector.get_path()
        p2 = self.target_selector.get_path()

        if not p1 or not p2:
            QMessageBox.warning(self, "Error", "Please select both folders.")
            return
        if p1 == p2:
            QMessageBox.warning(self, "Error", "Reference and Target folders cannot be the same.")
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Files in:\n{p2}\n\nthat match files in:\n{p1}\n\nWILL BE DELETED.\nAre you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.accept()

    def get_paths(self):
        return self.ref_selector.get_path(), self.target_selector.get_path()
