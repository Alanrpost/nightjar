"""Pick running process names for split tunneling, instead of typing .exe names
from memory."""

from __future__ import annotations

import psutil
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QListWidget, QListWidgetItem, QVBoxLayout

from .i18n import t


class ProcessPickerDialog(QDialog):
    def __init__(self, already_selected: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("process_picker_title"))
        self.setMinimumSize(360, 480)

        layout = QVBoxLayout(self)

        self.list_widget = QListWidget()
        for name in self._running_process_names():
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if name in already_selected else Qt.CheckState.Unchecked
            )
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _running_process_names() -> list[str]:
        names = set()
        for proc in psutil.process_iter(["name"]):
            name = proc.info.get("name")
            if name:
                names.add(name)
        return sorted(names, key=str.lower)

    def selected_names(self) -> list[str]:
        return [
            self.list_widget.item(i).text()
            for i in range(self.list_widget.count())
            if self.list_widget.item(i).checkState() == Qt.CheckState.Checked
        ]
