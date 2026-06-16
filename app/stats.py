"""Query sing-box's Clash-compatible API for cumulative traffic counters."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


def fetch_traffic(controller_address: str, timeout: float = 1.0) -> tuple[int, int] | None:
    """Return (download_total_bytes, upload_total_bytes) since the process started,
    or None if the API isn't reachable yet (e.g. sing-box still starting up)."""
    url = f"http://{controller_address}/connections"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            data = json.load(response)
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None

    download = data.get("downloadTotal")
    upload = data.get("uploadTotal")
    if not isinstance(download, int) or not isinstance(upload, int):
        return None
    return download, upload


def format_bytes(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def format_duration(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
