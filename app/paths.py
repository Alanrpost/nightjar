"""Shared filesystem locations for app data, binaries and logs."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "vless-client"


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA", str(Path.home()))
    path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def project_root() -> Path:
    # Frozen (PyInstaller) build: bin/ and assets/ ship next to the exe, not
    # nested under app/ - __file__ resolves into the bundle's internal data dir,
    # which doesn't share a layout with the exe's directory.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    # app/paths.py -> vless-client/
    return Path(__file__).resolve().parent.parent


def bin_dir() -> Path:
    return project_root() / "bin"


def assets_dir() -> Path:
    if getattr(sys, "frozen", False):
        return project_root() / "assets"
    return Path(__file__).resolve().parent / "assets"


def singbox_exe_path() -> Path:
    return bin_dir() / "sing-box.exe"


def profiles_file() -> Path:
    return app_data_dir() / "profiles.json"


def pid_file() -> Path:
    return app_data_dir() / "singbox.pid"


def log_file() -> Path:
    return app_data_dir() / "singbox.log"


def update_installer_path(version: str) -> Path:
    return app_data_dir() / f"Nightjar-Setup-{version}.exe"
