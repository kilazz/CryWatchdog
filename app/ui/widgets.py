# app/ui/widgets.py
from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QWidget,
)


class PathSelector(QWidget):
    """
    A composite widget containing a button and a line edit for selecting file/folder paths.
    """

    def __init__(self, label_text: str, is_file: bool = False, is_save: bool = False):
        super().__init__()
        self.is_file = is_file
        self.is_save = is_save

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.button = QPushButton(label_text)
        self.path_edit = QLineEdit()

        layout.addWidget(self.button)
        layout.addWidget(self.path_edit)

        self.button.clicked.connect(self._select_path)

    def _select_path(self):
        """Opens a file or directory dialog based on the widget's configuration."""
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
        """Returns the selected path as a Path object, or None if empty."""
        text = self.path_edit.text().strip()
        return Path(text) if text else None

    def set_path(self, path: Path):
        """Sets the text of the line edit to the given path."""
        self.path_edit.setText(str(path))
