"""Global split-tunneling settings: .exe names that bypass the VPN, applied to
whichever profile is currently active."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from .i18n import t
from .process_picker_dialog import ProcessPickerDialog


class SplitTunnelDialog(QDialog):
    def __init__(self, excluded_processes: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("split_tunnel_title"))
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)

        info = QLabel(t("split_tunnel_info"))
        info.setWordWrap(True)
        layout.addWidget(info)

        row = QHBoxLayout()
        self.processes_edit = QLineEdit(",".join(excluded_processes))
        self.processes_edit.setPlaceholderText("Spotify.exe,Steam.exe")
        pick_btn = QPushButton(t("split_tunnel_pick_btn"))
        pick_btn.clicked.connect(self._pick_processes)
        row.addWidget(self.processes_edit)
        row.addWidget(pick_btn)
        layout.addLayout(row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _pick_processes(self) -> None:
        current = [n.strip() for n in self.processes_edit.text().split(",") if n.strip()]
        dialog = ProcessPickerDialog(current, self)
        if dialog.exec() == ProcessPickerDialog.DialogCode.Accepted:
            self.processes_edit.setText(",".join(dialog.selected_names()))

    def result_processes(self) -> list[str]:
        return [p.strip() for p in self.processes_edit.text().split(",") if p.strip()]
