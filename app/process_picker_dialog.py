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
        # Windows process names are case-insensitive, and names typed by hand
        # often differ in case from what psutil reports.
        checked = {n.lower() for n in checked_names}
        running = self._running_process_names()
        running_lower = {n.lower() for n in running}
        # Previously selected apps that aren't running right now must stay in
        # the list (checked) - otherwise pressing OK silently drops them from
        # the split-tunnel list.
        not_running: list[str] = []
        seen: set[str] = set()
        for name in checked_names:
            key = name.lower()
            if key not in running_lower and key not in seen:
                seen.add(key)
                not_running.append(name)
        for name in not_running:
            self._add_item(name, True)
        for name in running:
            self._add_item(name, name.lower() in checked)

    def _add_item(self, name: str, is_checked: bool) -> None:
        item = QListWidgetItem(name)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked)
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
