"""Fetch and parse HTTP(S) subscription links: a URL that resolves to a list of
profile share links (vless://, ss://, trojan://, ...), the format used by most
panels (3x-ui, Marzban, and others) - usually the whole body is one base64
blob, sometimes it's already a plain newline-separated list."""

from __future__ import annotations

import base64
import binascii
import urllib.error
import urllib.request
from urllib.parse import urlparse

from .profile_parser import Profile, ProfileParseError, looks_like_profile_uri, parse_profile_uri

USER_AGENT = "Nightjar-subscription-client"


class SubscriptionError(Exception):
    pass


def looks_like_subscription_url(text: str) -> bool:
    text = text.strip()
    if not text or any(ch.isspace() for ch in text):
        return False
    parsed = urlparse(text)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _decode_subscription_body(text: str) -> str:
    """Try base64 first (stripping whitespace, since some panels line-wrap the
    blob); only trust the result if it actually looks like a link list.
    Otherwise assume the body is already a plain list of links."""
    compact = "".join(text.split())
    padded = compact + "=" * (-len(compact) % 4)
    for decoder in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            candidate = decoder(padded).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue
        if "://" in candidate:
            return candidate
    return text


def fetch_subscription_profiles(url: str, timeout: float = 10.0) -> list[Profile]:
    """Download the subscription body and parse every recognized link in it.
    Raises SubscriptionError if the URL can't be reached or contains no
    supported links."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise SubscriptionError(f"Failed to download subscription: {exc}") from exc

    decoded = _decode_subscription_body(raw.decode("utf-8", errors="ignore"))

    profiles: list[Profile] = []
    for line in decoded.splitlines():
        line = line.strip()
        if not line or not looks_like_profile_uri(line):
            continue
        try:
            profiles.append(parse_profile_uri(line))
        except ProfileParseError:
            continue

    if not profiles:
        raise SubscriptionError("No supported links found in the subscription")

    return profiles
