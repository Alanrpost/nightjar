"""Entry point: elevate to admin (required for TUN), clean up any leftover state
from a previous crash, then launch the GUI."""

from __future__ import annotations

import ctypes
import os
import sys


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def relaunch_as_admin() -> None:
    params = " ".join(f'"{arg}"' for arg in sys.argv[1:])
    if getattr(sys, "frozen", False):
        # Frozen build: sys.executable is the app's own exe - relaunch it directly.
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
    else:
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, f'-m app.main {params}', None, 1
        )


def _enable_per_monitor_dpi_awareness() -> None:
    """Must run before QApplication exists, so the window is created with the
    right DPI awareness context from the start."""
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except (AttributeError, OSError):
        pass


def main() -> int:
    _enable_per_monitor_dpi_awareness()

    # Explicit opt-in escape hatch for build verification (e.g. checking that a
    # PyInstaller bundle imports cleanly) without triggering a real UAC prompt.
    skip_admin_check = os.environ.get("VLESS_CLIENT_SKIP_ADMIN_CHECK") == "1"

    if not is_admin() and not skip_admin_check:
        relaunch_as_admin()
        return 0

    from . import cleanup

    cleanup.run_startup_cleanup()

    from . import tray_app

    return tray_app.run(start_minimized="--minimized" in sys.argv)


if __name__ == "__main__":
    sys.exit(main())
