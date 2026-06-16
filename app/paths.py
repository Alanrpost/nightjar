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
    # app/paths.py -> vless-client/
    return Path(__file__).resolve().parent.parent


def bin_dir() -> Path:
    return project_root() / "bin"


def assets_dir() -> Path:
    return Path(__file__).resolve().parent / "assets"


def singbox_exe_path() -> Path:
    return bin_dir() / "sing-box.exe"


def profiles_file() -> Path:
    return app_data_dir() / "profiles.json"


def pid_file() -> Path:
    return app_data_dir() / "singbox.pid"


def log_file() -> Path:
    return app_data_dir() / "singbox.log"
