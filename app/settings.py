"""App-wide settings (kill switch, auto-reconnect target, last active profile),
persisted in %APPDATA%\\vless-client\\settings.json."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from . import paths


@dataclass
class AppSettings:
    kill_switch_enabled: bool = True
    auto_connect_on_launch: bool = False
    last_active_profile: str = ""
    # Split tunneling: .exe names and/or domains, meaning depends on
    # split_tunnel_mode - either these are routed direct while everything else
    # goes through the VPN ("exclude", the default), or these are the only
    # ones routed through the VPN while everything else goes direct
    # ("include"). Domains match the site itself and any subdomain.
    excluded_processes: list[str] = field(default_factory=list)
    excluded_domains: list[str] = field(default_factory=list)
    split_tunnel_mode: str = "exclude"
    language: str = "ru"


def _settings_file():
    return paths.app_data_dir() / "settings.json"


def load_settings() -> AppSettings:
    path = _settings_file()
    if not path.exists():
        return AppSettings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return AppSettings()
    known_fields = AppSettings.__dataclass_fields__.keys()
    return AppSettings(**{k: v for k, v in raw.items() if k in known_fields})


def save_settings(settings: AppSettings) -> None:
    _settings_file().write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
