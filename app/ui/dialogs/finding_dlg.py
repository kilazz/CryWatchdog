# app/ui/dialogs/finding_dlg.py
from collections import defaultdict
from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QVBoxLayout,
)

from app.config import UIConfig


class UnusedAssetsDialog(QDialog):
    def __init__(self, parent, results: dict):
        super().__init__(parent)
        self.setWindowTitle(f"Unused Assets Report (Time: {results['duration']:.2f}s)")
        self.resize(600, 700)
        layout = QVBoxLayout(self)

        info_group = QGroupBox("Scan Summary")
        info_layout = QVBoxLayout(info_group)
        info_layout.addWidget(QLabel(f"Total Assets Scanned: {results['total_assets']:,}"))
        count_label = QLabel(f"Potential Unused Assets: {len(results['unused_files'])}")
        count_label.setStyleSheet(
            f"color: {UIConfig.COLOR_ERROR if results['unused_files'] else UIConfig.COLOR_SUCCESS}; font-weight: bold;"
        )
        info_layout.addWidget(count_label)
        layout.addWidget(info_group)

        layout.addWidget(QLabel("Orphaned Files:"))
        self.list_widget = QTreeWidget()
        self.list_widget.setHeaderLabel("File Path (Relative)")
        self.list_widget.setFont(UIConfig.FONT_MONOSPACE)

        for f in results["unused_files"]:
            item = QTreeWidgetItem([f])
            item.setForeground(0, QColor(UIConfig.COLOR_ERROR))
            self.list_widget.addTopLevelItem(item)
        layout.addWidget(self.list_widget)

        btn_box = QHBoxLayout()
        copy_btn = QPushButton("Copy List")
        copy_btn.clicked.connect(self._copy)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_box.addWidget(copy_btn)
        btn_box.addStretch()
        btn_box.addWidget(close_btn)
        layout.addLayout(btn_box)

    def _copy(self):
        text = "\n".join(
            [self.list_widget.topLevelItem(i).text(0) for i in range(self.list_widget.topLevelItemCount())]
        )
        QApplication.clipboard().setText(text)
        QMessageBox.information(self, "Copied", "Paths copied to clipboard.")


class MissingAssetsDialog(QDialog):
    def __init__(self, parent, results: dict):
        super().__init__(parent)
        self.missing_map = results.get("missing_map", {})
        self.setWindowTitle(f"Missing Assets Report (Time: {results['duration']:.2f}s)")
        self.resize(800, 600)
        layout = QVBoxLayout(self)

        info_layout = QHBoxLayout()
        count = len(self.missing_map)
        status = QLabel(f"Broken References: {count}")
        status.setStyleSheet(
            f"color: {UIConfig.COLOR_ERROR if count > 0 else UIConfig.COLOR_SUCCESS}; font-weight: bold;"
        )
        info_layout.addWidget(status)
        info_layout.addWidget(QLabel(f"(Scanned {results['total_scanned']} files)"))
        info_layout.addStretch()
        self.group_cb = QCheckBox("Group by File Extension")
        self.group_cb.toggled.connect(self._populate)
        info_layout.addWidget(self.group_cb)
        layout.addLayout(info_layout)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Missing Asset / Group", "Count / Ext"])
        self.tree.setColumnWidth(0, 500)
        self.tree.setFont(UIConfig.FONT_MONOSPACE)
        layout.addWidget(self.tree)

        btn_box = QHBoxLayout()
        copy_btn = QPushButton("Copy Report")
        copy_btn.clicked.connect(self._copy)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_box.addWidget(copy_btn)
        btn_box.addStretch()
        btn_box.addWidget(close_btn)
        layout.addLayout(btn_box)
        self._populate(False)

    def _populate(self, group):
        self.tree.clear()
        self.tree.setSortingEnabled(False)
        if group:
            groups = defaultdict(list)
            for path, containers in self.missing_map.items():
                groups[Path(path).suffix.lower() or "No Ext"].append((path, containers))
            for ext, items in sorted(groups.items()):
                group_item = QTreeWidgetItem([f"[{ext.upper()}]", f"{len(items)} files"])
                group_item.setForeground(0, QColor(UIConfig.COLOR_INFO))
                for path, containers in sorted(items, key=lambda x: len(x[1]), reverse=True):
                    self._add_item(group_item, path, containers)
                self.tree.addTopLevelItem(group_item)
            self.tree.expandAll()
        else:
            for path, containers in sorted(self.missing_map.items(), key=lambda x: len(x[1]), reverse=True):
                self._add_item(self.tree, path, containers)
        self.tree.setSortingEnabled(True)

    def _add_item(self, parent, path, containers):
        item = (
            QTreeWidgetItem([path, Path(path).suffix.lower()])
            if isinstance(parent, QTreeWidget)
            else QTreeWidgetItem([path, f"{len(containers)} refs"])
        )
        if not isinstance(parent, QTreeWidget):
            parent.addChild(item)
        else:
            parent.addTopLevelItem(item)
        item.setForeground(0, QColor(UIConfig.COLOR_ERROR))
        for c in containers:
            child = QTreeWidgetItem([f"↳ {c}", ""])
            child.setForeground(0, QColor("gray"))
            item.addChild(child)

    def _copy(self):
        lines = []
        it = QTreeWidgetItemIterator(self.tree)
        while it.value():
            item = it.value()
            indent = "\t" * (1 if item.parent() and item.parent().parent() else 0)
            lines.append(f"{indent}{item.text(0)}")
            it += 1
        QApplication.clipboard().setText("\n".join(lines))
        QMessageBox.information(self, "Copied", "Report copied.")
