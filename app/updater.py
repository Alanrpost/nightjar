"""Check GitHub Releases for a newer build and download its installer.

The app can't overwrite its own running executable, so applying an update
means: download the new Nightjar-Setup.exe, hand it off as a separate
process, then quit - Inno Setup does the actual file replacement and
relaunches the app once this process is no longer holding its files open."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

RELEASES_API_URL = "https://api.github.com/repos/Alanrpost/nightjar/releases/latest"
USER_AGENT = "Nightjar-updater"


class UpdateError(Exception):
    pass


@dataclass
class UpdateInfo:
    version: str
    download_url: str


def _version_tuple(version: str) -> tuple[int, ...]:
    parts = []
    for chunk in version.strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def check_for_update(current_version: str, timeout: float = 5.0) -> UpdateInfo | None:
    """Return info about a newer release, or None if already up to date or the
    check couldn't complete (no internet, GitHub unreachable, ...) - this runs
    unattended at startup and must never raise."""
    request = urllib.request.Request(
        RELEASES_API_URL,
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.load(response)
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return None

    latest_version = str(data.get("tag_name", "")).strip()
    if not latest_version or _version_tuple(latest_version) <= _version_tuple(current_version):
        return None

    download_url = ""
    for asset in data.get("assets", []):
        if str(asset.get("name", "")).lower().endswith(".exe"):
            download_url = asset.get("browser_download_url", "")
            break
    if not download_url:
        return None

    return UpdateInfo(version=latest_version.lstrip("vV"), download_url=download_url)


def download_installer(url: str, dest_path: Path, timeout: float = 120.0) -> None:
    """Stream the installer to dest_path. Raises UpdateError on failure."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            with dest_path.open("wb") as out:
                while chunk := response.read(1024 * 1024):
                    out.write(chunk)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        dest_path.unlink(missing_ok=True)
        raise UpdateError(f"Failed to download the update: {exc}") from exc
