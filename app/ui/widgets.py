from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QWidget
from qfluentwidgets import LineEdit, PushButton


class PathSelector(QWidget):
    def __init__(self, label_text: str, is_file: bool = False, is_save: bool = False, button_width: int = 130):
        super().__init__()
        self.is_file = is_file
        self.is_save = is_save

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.button = PushButton(label_text)
        if button_width > 0:
            self.button.setFixedWidth(button_width)

        self.path_edit = LineEdit()

        layout.addWidget(self.button)
        layout.addWidget(self.path_edit)

        self.button.clicked.connect(self._select_path)

    def _select_path(self):
        path = ""
        if self.is_file:
            path, _ = QFileDialog.getOpenFileName(self, "Select File")
        elif self.is_save:
            path, _ = QFileDialog.getSaveFileName(self, "Save File As", filter="Text Files (*.txt);;All Files (*)")
        else:
            path = QFileDialog.getExistingDirectory(self, "Select Folder")

        if path:
            self.path_edit.setText(path)

    def get_path(self) -> Path | None:
        text = self.path_edit.text().strip()
        return Path(text) if text else None

    def set_path(self, path: Path | str):
        self.path_edit.setText(str(path))
