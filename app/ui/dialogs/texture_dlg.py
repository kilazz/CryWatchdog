# app/ui/dialogs/texture_dlg.py
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import UIConfig


class TextureReportDialog(QDialog):
    """
    Dialog to display results of the Texture Validator task.
    Features tabs for Outdated and Missing textures.
    """

    def __init__(self, parent, results: dict):
        super().__init__(parent)
        self.setWindowTitle("Texture Validation Report")
        self.resize(800, 600)
        self.results = results

        layout = QVBoxLayout(self)

        # Summary Label
        summary_lbl = QLabel(results.get("summary", ""))
        summary_lbl.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(summary_lbl)

        # Tabs
        self.tabs = QTabWidget()

        self.tab_outdated = self._create_list_tab(
            results.get("outdated", []), "Outdated Source Files (Source is newer than .dds)", UIConfig.COLOR_WARNING
        )

        self.tab_missing = self._create_list_tab(
            results.get("missing", []),
            "Missing Compiled Files (Source exists, but .dds is missing)",
            UIConfig.COLOR_ERROR,
        )

        self.tabs.addTab(self.tab_outdated, f"Outdated ({len(results.get('outdated', []))})")
        self.tabs.addTab(self.tab_missing, f"Missing DDS ({len(results.get('missing', []))})")

        layout.addWidget(self.tabs)

        # Buttons
        btn_layout = QHBoxLayout()
        copy_btn = QPushButton("Copy Current List")
        copy_btn.clicked.connect(self._copy_current)

        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_box.rejected.connect(self.accept)

        btn_layout.addWidget(copy_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_box)
        layout.addLayout(btn_layout)

    def _create_list_tab(self, data: list, title: str, color_hex: str) -> QWidget:
        """Helper to create a tab page with a tree widget."""
        widget = QWidget()
        vbox = QVBoxLayout(widget)

        lbl = QLabel(title)
        vbox.addWidget(lbl)

        tree = QTreeWidget()
        tree.setHeaderLabel("Source File Path")
        tree.setFont(UIConfig.FONT_MONOSPACE)

        for path in data:
            item = QTreeWidgetItem([path])
            item.setForeground(0, QColor(color_hex))
            tree.addTopLevelItem(item)

        vbox.addWidget(tree)
        return widget

    def _copy_current(self):
        """Copies the contents of the currently active list to clipboard."""
        current_widget = self.tabs.currentWidget()
        # Find the QTreeWidget inside the current tab page
        tree = current_widget.findChild(QTreeWidget)

        if not tree or tree.topLevelItemCount() == 0:
            return

        lines = [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]

        QApplication.clipboard().setText("\n".join(lines))
        QMessageBox.information(self, "Copied", f"Copied {len(lines)} paths to clipboard.")
