"""Register/unregister a Windows Scheduled Task that launches the app at logon.

A plain HKCU "Run" key would trigger a UAC prompt every boot (TUN needs admin).
A Scheduled Task with RunLevel=Highest, registered while already elevated, runs
elevated at logon with no prompt - the standard trick for auto-elevating startup apps.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from . import paths

TASK_NAME = "VlessClientAutostart"


def _pythonw_executable() -> str:
    """Prefer pythonw.exe (no console window) if it sits next to sys.executable."""
    exe = sys.executable
    pythonw = exe.lower().replace("python.exe", "pythonw.exe")
    if pythonw != exe.lower() and Path(pythonw).exists():
        return pythonw
    return exe


def is_enabled() -> bool:
    result = subprocess.run(
        ["schtasks", "/query", "/tn", TASK_NAME],
        capture_output=True,
        text=True,
        encoding="cp866",
        errors="replace",
    )
    return result.returncode == 0


def enable() -> None:
    python_exe = _pythonw_executable()
    project_root = paths.project_root()
    command = f'cmd /c "cd /d \\"{project_root}\\" && \\"{python_exe}\\" -m app.main --minimized"'

    result = subprocess.run(
        [
            "schtasks", "/create",
            "/tn", TASK_NAME,
            "/tr", command,
            "/sc", "onlogon",
            "/rl", "highest",
            "/f",
        ],
        capture_output=True,
        text=True,
        encoding="cp866",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Не удалось создать задачу автозапуска: {result.stderr or result.stdout}"
        )


def disable() -> None:
    subprocess.run(
        ["schtasks", "/delete", "/tn", TASK_NAME, "/f"],
        capture_output=True,
        text=True,
        encoding="cp866",
        errors="replace",
    )
