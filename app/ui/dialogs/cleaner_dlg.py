from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QVBoxLayout
from qfluentwidgets import CardWidget, CheckBox, ComboBox

from app.config import UIConfig


class CleanerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Clean & Normalize Assets")
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        self.options_widgets = {}

        norm_group = CardWidget()
        norm_layout = QVBoxLayout(norm_group)
        self.options_widgets["normalize_encoding_check"] = CheckBox("Enable Normalization")
        self.options_widgets["normalize_encoding_check"].setChecked(True)
        norm_layout.addWidget(self.options_widgets["normalize_encoding_check"])

        enc_box = QHBoxLayout()
        enc_box.addWidget(QLabel("Target Encoding:"))
        self.options_widgets["target_encoding"] = ComboBox()
        self.options_widgets["target_encoding"].addItems(["UTF-8", "UTF-16", "ISO-8859-1"])
        self.options_widgets["target_encoding"].setCurrentText("UTF-8")
        enc_box.addWidget(self.options_widgets["target_encoding"])
        enc_box.addStretch()
        norm_layout.addLayout(enc_box)

        nl_box = QHBoxLayout()
        nl_box.addWidget(QLabel("Line Endings:"))
        self.options_widgets["newline_type"] = ComboBox()
        self.options_widgets["newline_type"].addItems(["CRLF (Windows)", "LF (Unix/macOS)", "CR (Classic Mac OS)"])
        nl_box.addWidget(self.options_widgets["newline_type"])
        nl_box.addStretch()
        norm_layout.addLayout(nl_box)
        layout.addWidget(norm_group)

        self.options_widgets["strip_bom"] = CheckBox("Strip non-text file headers (e.g., from XMLs)")
        self.options_widgets["strip_bom"].setChecked(True)
        layout.addWidget(self.options_widgets["strip_bom"])

        self.options_widgets["trim_whitespace"] = CheckBox("Trim Trailing Whitespace")
        self.options_widgets["trim_whitespace"].setChecked(True)
        layout.addWidget(self.options_widgets["trim_whitespace"])

        path_group = CardWidget()
        path_layout = QVBoxLayout(path_group)
        self.options_widgets["normalize_paths"] = CheckBox("Normalize path separators to forward slashes ( / )")
        self.options_widgets["normalize_paths"].setChecked(True)
        path_layout.addWidget(self.options_widgets["normalize_paths"])

        self.options_widgets["resolve_redundant_paths"] = CheckBox("Resolve redundant paths (e.g., 'folder/../file')")
        self.options_widgets["resolve_redundant_paths"].setChecked(True)
        path_layout.addWidget(self.options_widgets["resolve_redundant_paths"])

        self.options_widgets["convert_to_lowercase"] = CheckBox("Convert asset paths inside files to lowercase")
        self.options_widgets["convert_to_lowercase"].setChecked(True)
        path_layout.addWidget(self.options_widgets["convert_to_lowercase"])
        layout.addWidget(path_group)

        warning = QLabel("WARNING: This is an irreversible operation. Please ensure you have a backup.")
        warning.setStyleSheet(f"color: {UIConfig.COLOR_ERROR};")
        layout.addWidget(warning, 0, Qt.AlignmentFlag.AlignCenter)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_options(self) -> dict:
        params = {
            k: v.isChecked() if isinstance(v, CheckBox) else v.currentText() for k, v in self.options_widgets.items()
        }
        params["normalize_encoding"] = params.pop("normalize_encoding_check")
        params["newline_type_label"] = params.pop("newline_type")
        return params
