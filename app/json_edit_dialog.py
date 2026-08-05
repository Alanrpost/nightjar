"""Raw sing-box config editor for a single profile, similar to Happ's JSON editor:
power users can see and tweak exactly what gets passed to the engine."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from . import paths
from .i18n import t
from .profile_parser import Profile
from .singbox_config import build_config


class JsonEditDialog(QDialog):
    def __init__(self, profile: Profile, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("json_edit_title", name=profile.name))
        self.setMinimumSize(700, 600)
        self.original_profile = profile
        self.result_raw_config: str | None = None  # None = unchanged, "" = reset to auto

        layout = QVBoxLayout(self)

        info = QLabel(t("json_edit_info"))
        info.setWordWrap(True)
        layout.addWidget(info)

        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont("Consolas", 10))
        starting_text = profile.raw_config.strip() or json.dumps(
            build_config(profile), indent=2
        )
        self.editor.setPlainText(starting_text)
        layout.addWidget(self.editor)

        reset_row = QHBoxLayout()
        reset_btn = QPushButton(t("json_edit_reset_btn"))
        reset_btn.clicked.connect(self._reset_to_auto)
        reset_row.addWidget(reset_btn)
        reset_row.addStretch()
        layout.addLayout(reset_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _reset_to_auto(self) -> None:
        self.editor.setPlainText(json.dumps(build_config(self.original_profile), indent=2))

    def _on_save(self) -> None:
        text = self.editor.toPlainText().strip()

        if not text:
            self.result_raw_config = ""
            self.accept()
            return

        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            QMessageBox.warning(self, t("dlg_invalid_json_title"), t("dlg_invalid_json_body", error=exc))
            return

        validation_error = self._validate_with_singbox(text)
        if validation_error:
            proceed = QMessageBox.question(
                self,
                t("dlg_singbox_rejected_title"),
                t("dlg_singbox_rejected_body", error=validation_error),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if proceed != QMessageBox.StandardButton.Yes:
                return

        self.result_raw_config = text
        self.accept()

    def _validate_with_singbox(self, config_text: str) -> str | None:
        """Best-effort validation via `sing-box check`. Returns an error message, or
        None if valid or if sing-box.exe isn't available to check against."""
        exe = paths.singbox_exe_path()
        if not exe.exists():
            return None

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(config_text)
            tmp_path = Path(tmp.name)

        try:
            result = subprocess.run(
                [str(exe), "check", "-c", str(tmp_path)],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode != 0:
                return (result.stderr or result.stdout or t("unknown_error")).strip()
            return None
        except (subprocess.SubprocessError, OSError):
            return None
        finally:
            tmp_path.unlink(missing_ok=True)
