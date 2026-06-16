"""Entry point: elevate to admin (required for TUN), clean up any leftover state
from a previous crash, then launch the GUI."""

from __future__ import annotations

import ctypes
import sys


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def relaunch_as_admin() -> None:
    params = " ".join(f'"{arg}"' for arg in sys.argv)
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, f'-m app.main {params}', None, 1
    )


def main() -> int:
    if not is_admin():
        relaunch_as_admin()
        return 0

    from . import cleanup

    cleanup.run_startup_cleanup()

    from . import tray_app

    return tray_app.run(start_minimized="--minimized" in sys.argv)


if __name__ == "__main__":
    sys.exit(main())
