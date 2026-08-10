from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMessageBox, QVBoxLayout
from qfluentwidgets import CardWidget, InfoBar, LineEdit, PushButton

from app.config import AppConfig
from app.tasks.packer import AssetPacker, AssetUnpacker
from app.ui.widgets import PathSelector


class PackerDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.main_window = parent
        self.setWindowTitle("Text Packer Tool")
        self.setMinimumWidth(620)

        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # --- Pack Section ---
        pack_group = CardWidget()
        pack_layout = QVBoxLayout(pack_group)
        pack_layout.setSpacing(8)

        self.pack_src = PathSelector("Source Folder...", button_width=130)
        self.pack_out = PathSelector("Output File...", is_save=True, button_width=130)

        ext_layout = QHBoxLayout()
        ext_layout.setSpacing(8)
        ext_label = QLabel("Extensions:")
        ext_label.setFixedWidth(130)
        self.pack_ext = LineEdit()

        ext_layout.addWidget(ext_label)
        ext_layout.addWidget(self.pack_ext)

        btn_pack = PushButton("Pack Files")
        btn_pack.clicked.connect(self._pack)

        pack_layout.addWidget(self.pack_src)
        pack_layout.addWidget(self.pack_out)
        pack_layout.addLayout(ext_layout)
        pack_layout.addWidget(btn_pack)
        layout.addWidget(pack_group)

        # --- Unpack Section ---
        unpack_group = CardWidget()
        unpack_layout = QVBoxLayout(unpack_group)
        unpack_layout.setSpacing(8)

        self.unpack_src = PathSelector("Archive File...", is_file=True, button_width=130)
        self.unpack_out = PathSelector("Output Folder...", button_width=130)
        btn_unpack = PushButton("Unpack File")
        btn_unpack.clicked.connect(self._unpack)

        unpack_layout.addWidget(self.unpack_src)
        unpack_layout.addWidget(self.unpack_out)
        unpack_layout.addWidget(btn_unpack)
        layout.addWidget(unpack_group)

        # --- Bottom Control ---
        close_layout = QHBoxLayout()
        close_layout.addStretch()
        btn_close = PushButton("Close")
        btn_close.clicked.connect(self.accept)
        close_layout.addWidget(btn_close)
        layout.addLayout(close_layout)

    def _load_settings(self):
        s = AppConfig.PACKER_SETTINGS

        pack_src = s.get("pack_src", "")
        if not pack_src and self.main_window.project_root:
            pack_src = str(self.main_window.project_root)
        self.pack_src.set_path(pack_src)

        self.pack_out.set_path(s.get("pack_out", ""))
        self.pack_ext.setText(s.get("pack_ext", ".lua, .xml, .txt, .cfg"))

        self.unpack_src.set_path(s.get("unpack_src", ""))

        unpack_out = s.get("unpack_out", "")
        if not unpack_out and self.main_window.project_root:
            unpack_out = str(self.main_window.project_root)
        self.unpack_out.set_path(unpack_out)

    def _save_settings(self):
        AppConfig.PACKER_SETTINGS["pack_src"] = str(self.pack_src.get_path() or "")
        AppConfig.PACKER_SETTINGS["pack_out"] = str(self.pack_out.get_path() or "")
        AppConfig.PACKER_SETTINGS["pack_ext"] = self.pack_ext.text().strip()
        AppConfig.PACKER_SETTINGS["unpack_src"] = str(self.unpack_src.get_path() or "")
        AppConfig.PACKER_SETTINGS["unpack_out"] = str(self.unpack_out.get_path() or "")
        AppConfig.save()

    def _pack(self):
        src, out = self.pack_src.get_path(), self.pack_out.get_path()
        if not (src and out):
            InfoBar.warning("Missing Paths", "Please select both Source Folder and Output File.", parent=self)
            return

        self._save_settings()

        exts = tuple(e.strip().lower() for e in self.pack_ext.text().split(",") if e.strip())
        self.main_window.run_task(
            lambda: AssetPacker(
                src,
                out,
                exts,
                progress_callback=lambda c, t: self.main_window.core_signals.progressUpdated.emit(c, t),
            ).run(),
            lambda res: InfoBar.success("Packer", res.summary, parent=self),
        )

    def _unpack(self):
        src, out = self.unpack_src.get_path(), self.unpack_out.get_path()
        if not (src and out):
            InfoBar.warning("Missing Paths", "Please select both Archive File and Output Folder.", parent=self)
            return

        self._save_settings()

        if QMessageBox.question(self, "Confirm", "Overwrite existing files?") == QMessageBox.StandardButton.Yes:
            self.main_window.run_task(
                lambda: AssetUnpacker(
                    src,
                    out,
                    progress_callback=lambda c, t: self.main_window.core_signals.progressUpdated.emit(c, t),
                ).run(),
                lambda res: InfoBar.success("Unpacker", res.summary, parent=self),
            )

    def closeEvent(self, event):
        self._save_settings()
        super().closeEvent(event)
