from typing import ClassVar

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QTreeWidgetItem,
    QVBoxLayout,
)
from qfluentwidgets import InfoBar, PushButton, TreeWidget

from app.config import UIConfig


class AnalysisReportDialog(QDialog):
    EXT_CATEGORIES: ClassVar[dict[str, set[str]]] = {
        "Textures": {".dds", ".tif", ".tiff", ".png", ".jpg", ".tga"},
        "Models": {".cgf", ".cga", ".chr", ".skin", ".fbx", ".obj"},
        "Scripts": {".lua", ".xml", ".mtl", ".json", ".cfg", ".ini"},
        "Audio": {".wav", ".ogg", ".mp3", ".fsb", ".fdp"},
        "Other": set(),
    }

    def __init__(self, parent, header_text: str, prepared_data: dict):
        super().__init__(parent)
        self.setWindowTitle("Analysis Report")
        self.resize(600, 500)

        layout = QVBoxLayout(self)

        self.header_lbl = QLabel(header_text)
        self.header_lbl.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(self.header_lbl)

        self.tree = TreeWidget()
        self.tree.setHeaderLabels(["Category / Extension", "Files Count"])
        self.tree.setFont(UIConfig.FONT_MONOSPACE)
        self.tree.setColumnWidth(0, 350)
        layout.addWidget(self.tree)

        self._populate(prepared_data)

        btn_layout = QHBoxLayout()

        self.copy_btn = PushButton("Copy Report")
        self.copy_btn.clicked.connect(self._copy_to_clipboard)
        btn_layout.addWidget(self.copy_btn)

        btn_layout.addStretch()

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        btn_layout.addWidget(btns)

        layout.addLayout(btn_layout)

    def _populate(self, prepared_data: dict):
        self.tree.clear()

        for cat in self.EXT_CATEGORIES:
            content = prepared_data.get(cat)
            if not content:
                continue

            cat_item = QTreeWidgetItem([cat, ""])
            cat_item.setForeground(0, QColor(UIConfig.COLOR_INFO))
            self.tree.addTopLevelItem(cat_item)

            if isinstance(content, dict):
                total_count = sum(content.values())
                sorted_items = sorted(content.items(), key=lambda x: x[1], reverse=True)
                for ext, count in sorted_items:
                    ext_item = QTreeWidgetItem([ext, str(count)])
                    cat_item.addChild(ext_item)
                cat_item.setText(1, f"Total: {total_count}")

            elif isinstance(content, str):
                lines = [line.strip() for line in content.strip().split("\n") if line.strip()]
                total_count = 0
                for line in lines:
                    if ":" in line:
                        ext, count_str = line.split(":", 1)
                        try:
                            count = int(count_str.strip())
                            total_count += count
                            ext_item = QTreeWidgetItem([ext.strip(), str(count)])
                        except ValueError:
                            ext_item = QTreeWidgetItem([ext.strip(), count_str.strip()])
                        cat_item.addChild(ext_item)
                cat_item.setText(1, f"Total: {total_count}")

        self.tree.expandAll()

    def _copy_to_clipboard(self):
        lines = [self.header_lbl.text(), "=" * 50]

        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            cat_item = root.child(i)
            lines.append(f"\n[{cat_item.text(0)}] — {cat_item.text(1)}")
            for j in range(cat_item.childCount()):
                child = cat_item.child(j)
                lines.append(f"  {child.text(0):<12} : {child.text(1)}")

        structured_text = "\n".join(lines)
        QApplication.clipboard().setText(structured_text)
        InfoBar.success("Success", "Report copied to clipboard.", parent=self)
