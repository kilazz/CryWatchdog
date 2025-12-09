# app/ui/dialogs/tod_dlg.py
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)

from app.ui.widgets import PathSelector


class TimeOfDayDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TimeOfDay Converter (CE3 -> CE5)")
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Select a legacy TimeOfDay.xml file to convert."))
        self.file_selector = PathSelector("Select File...", is_file=True)
        layout.addWidget(self.file_selector)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_file(self):
        return self.file_selector.get_path()
