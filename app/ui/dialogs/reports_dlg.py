# app/ui/dialogs/reports_dlg.py
from typing import ClassVar

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from app.config import UIConfig


class AnalysisReportDialog(QDialog):
    EXT_CATEGORIES: ClassVar[dict[str, set[str]]] = {
        "Textures": {".dds", ".tif", ".tiff", ".png", ".jpg", ".tga"},
        "Models": {".cgf", ".cga", ".chr", ".skin", ".fbx", ".obj"},
        "Scripts": {".lua", ".xml", ".mtl", ".json", ".cfg", ".ini"},
        "Audio": {".wav", ".ogg", ".mp3", ".fsb", ".fdp"},
        "Other": {},
    }

    def __init__(self, parent, header_text: str, prepared_data: dict):
        super().__init__(parent)
        self.setWindowTitle("Analysis Report")
        self.resize(1000, 600)

        # Renamed 'l' to 'layout' to fix E741
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(header_text))
        cols = QHBoxLayout()
        layout.addLayout(cols)

        for cat in self.EXT_CATEGORIES:
            if txt := prepared_data.get(cat):
                v = QVBoxLayout()
                lbl = QLabel(f"--- {cat} ---")
                lbl.setFont(UIConfig.FONT_MONOSPACE)
                v.addWidget(lbl)
                content = QLabel(txt)
                content.setFont(UIConfig.FONT_MONOSPACE)
                content.setAlignment(Qt.AlignmentFlag.AlignTop)
                v.addWidget(content)
                v.addStretch()
                cols.addLayout(v)

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
