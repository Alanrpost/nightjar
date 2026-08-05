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
from .i18n import t

TASK_NAME = "NightjarAutostart"
# Renamed from the app's old name - still cleaned up/recognized so upgrading
# users don't end up with an orphaned task or a wrong "off" checkbox.
_LEGACY_TASK_NAME = "VlessClientAutostart"


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
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode == 0:
        return True
    # Fall back to the pre-rename task name so an upgrading user's existing
    # autostart still shows as enabled instead of silently reading as off.
    legacy = subprocess.run(
        ["schtasks", "/query", "/tn", _LEGACY_TASK_NAME],
        capture_output=True,
        text=True,
        encoding="cp866",
        errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return legacy.returncode == 0


def _autostart_command() -> str:
    if getattr(sys, "frozen", False):
        # Frozen build: sys.executable is the app's own exe - run it directly.
        return f'"{sys.executable}" --minimized'
    python_exe = _pythonw_executable()
    project_root = paths.project_root()
    return f'cmd /c "cd /d \\"{project_root}\\" && \\"{python_exe}\\" -m app.main --minimized"'


def enable() -> None:
    command = _autostart_command()

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
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode != 0:
        raise RuntimeError(t("autostart_create_failed", error=result.stderr or result.stdout))

    # Clean up the pre-rename task, if any, so it doesn't linger as a duplicate.
    subprocess.run(
        ["schtasks", "/delete", "/tn", _LEGACY_TASK_NAME, "/f"],
        capture_output=True,
        text=True,
        encoding="cp866",
        errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def disable() -> None:
    for name in (TASK_NAME, _LEGACY_TASK_NAME):
        subprocess.run(
            ["schtasks", "/delete", "/tn", name, "/f"],
            capture_output=True,
            text=True,
            encoding="cp866",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
