"""Persist imported profiles (any supported protocol) to a JSON file in %APPDATA%."""

from __future__ import annotations

import json
from dataclasses import asdict

from . import paths
from .profile_parser import Profile


def load_profiles() -> list[Profile]:
    path = paths.profiles_file()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    known_fields = Profile.__dataclass_fields__.keys()
    return [Profile(**{k: v for k, v in item.items() if k in known_fields}) for item in raw]


def save_profiles(profiles: list[Profile]) -> None:
    path = paths.profiles_file()
    path.write_text(
        json.dumps([asdict(p) for p in profiles], indent=2),
        encoding="utf-8",
    )


def add_profile(profile: Profile) -> list[Profile]:
    profiles = load_profiles()
    profiles = [p for p in profiles if p.name != profile.name]
    profiles.append(profile)
    save_profiles(profiles)
    return profiles


def remove_profile(name: str) -> list[Profile]:
    profiles = [p for p in load_profiles() if p.name != name]
    save_profiles(profiles)
    return profiles


def update_profile(original_name: str, new_profile: Profile) -> list[Profile]:
    """Replace the profile that used to be named `original_name` with `new_profile`."""
    profiles = load_profiles()
    if original_name != new_profile.name and any(
        p.name == new_profile.name for p in profiles if p.name != original_name
    ):
        raise ValueError(f"Профиль с именем '{new_profile.name}' уже существует")

    profiles = [new_profile if p.name == original_name else p for p in profiles]
    save_profiles(profiles)
    return profiles
