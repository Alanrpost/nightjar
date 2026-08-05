"""Pick running process names for split tunneling, instead of typing .exe names
from memory."""

from __future__ import annotations

import psutil
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from .i18n import t


class ProcessPickerDialog(QDialog):
    def __init__(self, already_selected: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("process_picker_title"))
        self.setMinimumSize(360, 480)

        layout = QVBoxLayout(self)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)
        self._populate(already_selected)

        bottom_row = QHBoxLayout()
        refresh_btn = QPushButton(t("process_picker_refresh_btn"))
        refresh_btn.clicked.connect(self._refresh)
        bottom_row.addWidget(refresh_btn)
        bottom_row.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        bottom_row.addWidget(buttons)
        layout.addLayout(bottom_row)

    def _populate(self, checked_names: list[str]) -> None:
        self.list_widget.clear()
        checked = set(checked_names)
        for name in self._running_process_names():
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if name in checked else Qt.CheckState.Unchecked
            )
            self.list_widget.addItem(item)

    def _refresh(self) -> None:
        # Re-scan running processes (e.g. an app launched after this dialog was
        # already open) without losing checkmarks already made this session.
        self._populate(self.selected_names())

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
