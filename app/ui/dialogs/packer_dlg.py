# app/ui/dialogs/packer_dlg.py
from PySide6.QtWidgets import (
    QDialog,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.tasks.packer import AssetPacker, AssetUnpacker
from app.ui.widgets import PathSelector


class PackerDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.main_window = parent
        self.setWindowTitle("Text Packer Tool")
        self.setMinimumWidth(600)
        layout = QVBoxLayout(self)

        pack_group = QGroupBox("Pack Files")
        pack_layout = QVBoxLayout(pack_group)
        self.pack_src = PathSelector("Source Folder...")
        self.pack_out = PathSelector("Output File...", is_save=True)
        self.pack_ext = QLineEdit(".lua, .xml, .txt, .cfg")
        pack_layout.addWidget(self.pack_src)
        pack_layout.addWidget(self.pack_out)
        pack_layout.addWidget(QLabel("Extensions:"))
        pack_layout.addWidget(self.pack_ext)
        btn_pack = QPushButton("Pack Files")
        btn_pack.clicked.connect(self._pack)
        pack_layout.addWidget(btn_pack)
        layout.addWidget(pack_group)

        unpack_group = QGroupBox("Unpack File")
        unpack_layout = QVBoxLayout(unpack_group)
        self.unpack_src = PathSelector("Archive File...", is_file=True)
        self.unpack_out = PathSelector("Output Folder...")
        btn_unpack = QPushButton("Unpack File")
        btn_unpack.clicked.connect(self._unpack)
        unpack_layout.addWidget(self.unpack_src)
        unpack_layout.addWidget(self.unpack_out)
        unpack_layout.addWidget(btn_unpack)
        layout.addWidget(unpack_group)

        if self.main_window.project_root:
            self.pack_src.set_path(self.main_window.project_root)
            self.unpack_out.set_path(self.main_window.project_root)

    def _pack(self):
        src, out = self.pack_src.get_path(), self.pack_out.get_path()
        if not (src and out):
            return
        exts = tuple(e.strip().lower() for e in self.pack_ext.text().split(","))
        self.main_window.run_task(lambda: AssetPacker(src, out, exts, self.main_window.core_signals).run())
        self.accept()

    def _unpack(self):
        src, out = self.unpack_src.get_path(), self.unpack_out.get_path()
        if not (src and out):
            return
        if QMessageBox.question(self, "Confirm", "Overwrite existing?") == QMessageBox.Yes:
            self.main_window.run_task(lambda: AssetUnpacker(src, out, self.main_window.core_signals).run())
            self.accept()
