"""Detect and remove leftover state (orphan sing-box process / TUN adapter) from a
previous crash, so the user never has to reboot to get their network back.

Run this once at application startup, before anything else touches the network.
"""

from __future__ import annotations

import signal
import subprocess
import time

import psutil

from . import paths
from .singbox_config import TUN_INTERFACE_NAME

GRACEFUL_STOP_TIMEOUT = 5.0


def _kill_orphan_process() -> None:
    pid_path = paths.pid_file()
    if not pid_path.exists():
        return

    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        pid_path.unlink(missing_ok=True)
        return

    if not psutil.pid_exists(pid):
        pid_path.unlink(missing_ok=True)
        return

    try:
        proc = psutil.Process(pid)
        if "sing-box" not in proc.name().lower():
            # PID was recycled by an unrelated process; leave it alone.
            pid_path.unlink(missing_ok=True)
            return
    except psutil.Error:
        pid_path.unlink(missing_ok=True)
        return

    try:
        import os

        os.kill(pid, signal.CTRL_BREAK_EVENT)
        proc.wait(timeout=GRACEFUL_STOP_TIMEOUT)
    except (psutil.TimeoutExpired, OSError, ValueError):
        try:
            proc.kill()
            proc.wait(timeout=GRACEFUL_STOP_TIMEOUT)
        except psutil.Error:
            pass

    pid_path.unlink(missing_ok=True)


def _remove_orphan_tun_adapter() -> None:
    """sing-box normally tears its Wintun adapter down on graceful exit. After a
    force-kill the OS usually reclaims it too, but if it's still visible, remove it
    so stale routes bound to it can't keep the network half-broken."""
    check_cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        f"(Get-NetAdapter -Name '{TUN_INTERFACE_NAME}' -ErrorAction SilentlyContinue) -ne $null",
    ]
    try:
        result = subprocess.run(check_cmd, capture_output=True, text=True, timeout=10)
    except (subprocess.SubprocessError, OSError):
        return

    if "True" not in result.stdout:
        return

    remove_cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        f"Remove-NetAdapter -Name '{TUN_INTERFACE_NAME}' -Confirm:$false -ErrorAction SilentlyContinue",
    ]
    try:
        subprocess.run(remove_cmd, capture_output=True, text=True, timeout=10)
    except (subprocess.SubprocessError, OSError):
        pass


def run_startup_cleanup() -> None:
    _kill_orphan_process()
    time.sleep(0.5)  # give the OS a beat to release the adapter after process exit
    _remove_orphan_tun_adapter()
