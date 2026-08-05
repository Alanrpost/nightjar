"""Global split-tunneling settings: a list of .exe names plus a mode - either
those apps bypass the VPN and everything else is tunneled, or those apps are
the only ones tunneled and everything else goes direct. Applied to whichever
profile is currently active."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from .i18n import t
from .process_picker_dialog import ProcessPickerDialog


class SplitTunnelDialog(QDialog):
    def __init__(
        self,
        excluded_processes: list[str],
        split_tunnel_mode: str = "exclude",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("split_tunnel_title"))
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)

        self.exclude_radio = QRadioButton(t("split_tunnel_mode_exclude"))
        self.include_radio = QRadioButton(t("split_tunnel_mode_include"))
        if split_tunnel_mode == "include":
            self.include_radio.setChecked(True)
        else:
            self.exclude_radio.setChecked(True)
        self.exclude_radio.toggled.connect(self._update_info_text)
        layout.addWidget(self.exclude_radio)
        layout.addWidget(self.include_radio)

        self.info_label = QLabel()
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)
        self._update_info_text()

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

    def _update_info_text(self) -> None:
        key = "split_tunnel_info_include" if self.include_radio.isChecked() else "split_tunnel_info_exclude"
        self.info_label.setText(t(key))

    def _pick_processes(self) -> None:
        current = [n.strip() for n in self.processes_edit.text().split(",") if n.strip()]
        dialog = ProcessPickerDialog(current, self)
        if dialog.exec() == ProcessPickerDialog.DialogCode.Accepted:
            self.processes_edit.setText(",".join(dialog.selected_names()))

    def result_processes(self) -> list[str]:
        return [p.strip() for p in self.processes_edit.text().split(",") if p.strip()]

    def result_mode(self) -> str:
        return "include" if self.include_radio.isChecked() else "exclude"
