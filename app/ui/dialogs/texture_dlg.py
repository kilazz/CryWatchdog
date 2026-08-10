from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QTabWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import InfoBar, PushButton, TreeWidget

from app.config import UIConfig

if TYPE_CHECKING:
    from app.tasks.models import TextureValidatorResult


class TextureReportDialog(QDialog):
    def __init__(self, parent, results: TextureValidatorResult):
        super().__init__(parent)
        self.setWindowTitle("Texture Validation Report")
        self.resize(800, 600)
        self.results = results

        layout = QVBoxLayout(self)

        summary_lbl = QLabel(results.summary)
        summary_lbl.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(summary_lbl)

        self.tabs = QTabWidget()

        self.tab_outdated = self._create_list_tab(
            results.outdated, "Outdated Source Files (Source is newer than .dds)", UIConfig.COLOR_WARNING
        )

        self.tab_missing = self._create_list_tab(
            results.missing,
            "Missing Compiled Files (Source exists, but .dds is missing)",
            UIConfig.COLOR_ERROR,
        )

        self.tabs.addTab(self.tab_outdated, f"Outdated ({len(results.outdated)})")
        self.tabs.addTab(self.tab_missing, f"Missing DDS ({len(results.missing)})")

        layout.addWidget(self.tabs)

        btn_layout = QHBoxLayout()
        copy_btn = PushButton("Copy Current List")
        copy_btn.clicked.connect(self._copy_current)

        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_box.rejected.connect(self.accept)

        btn_layout.addWidget(copy_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_box)
        layout.addLayout(btn_layout)

    def _create_list_tab(self, data: list, title: str, color_hex: str) -> QWidget:
        widget = QWidget()
        vbox = QVBoxLayout(widget)

        lbl = QLabel(title)
        vbox.addWidget(lbl)

        tree = TreeWidget()
        tree.setHeaderLabel("Source File Path")
        tree.setFont(UIConfig.FONT_MONOSPACE)

        for path in data:
            item = QTreeWidgetItem([path])
            item.setForeground(0, QColor(color_hex))
            tree.addTopLevelItem(item)

        vbox.addWidget(tree)
        return widget

    def _copy_current(self):
        current_widget = self.tabs.currentWidget()
        if not current_widget:
            return

        tree = current_widget.findChild(TreeWidget)

        if not tree or tree.topLevelItemCount() == 0:
            return

        lines = [item.text(0) for i in range(tree.topLevelItemCount()) if (item := tree.topLevelItem(i))]

        QApplication.clipboard().setText("\n".join(lines))
        InfoBar.success("Copied", f"Copied {len(lines)} paths to clipboard.", parent=self)
