"""Look up the public IP/country of whatever exit the current request goes out
through - used to show the VPN exit IP once a tunnel is up. Relies on the OS
routing table doing its job: once sing-box's TUN adapter is the default route,
this process's own traffic (including this lookup) goes out through the tunnel
same as everything else, so the IP it reports back is the exit IP, not the
machine's real one."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

# IPinfo Lite - low-sensitivity token scoped to this free tier, fine to ship
# in a locally-run desktop app. Don't reuse it for anything beyond IP lookups.
IPINFO_TOKEN = "f7c2aed7985088"
IPINFO_URL = "https://api.ipinfo.io/lite/me"


def fetch_exit_ip_info(timeout: float = 5.0) -> tuple[str, str] | None:
    """Return (ip, country_name) for whatever this process's traffic currently
    exits through, or None if the lookup fails (no internet yet, API down,
    tunnel still coming up, ...)."""
    request = urllib.request.Request(
        IPINFO_URL, headers={"Authorization": f"Bearer {IPINFO_TOKEN}"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.load(response)
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None

    ip = data.get("ip")
    country = data.get("country")
    if not ip or not country:
        return None
    return ip, country
