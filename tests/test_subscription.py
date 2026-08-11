import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app import subscription


def test_looks_like_subscription_url_accepts_http_and_https():
    assert subscription.looks_like_subscription_url("https://sub.example.com:8443/sub/abc")
    assert subscription.looks_like_subscription_url("http://example.com/sub")


def test_looks_like_subscription_url_rejects_profile_links_and_junk():
    assert not subscription.looks_like_subscription_url("vless://uuid@host:443")
    assert not subscription.looks_like_subscription_url("not a url at all")
    assert not subscription.looks_like_subscription_url("https://example.com/sub\nhttps://x")
    assert not subscription.looks_like_subscription_url("")


def test_fetch_subscription_profiles_parses_base64_body(monkeypatch):
    links = (
        "vless://11111111-2222-3333-4444-555555555555@example.com:443?encryption=none#A\n"
        "trojan://password@example.org:443?security=tls#B\n"
        "not-a-real-link\n"
    )
    blob = base64.b64encode(links.encode())

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return blob

    monkeypatch.setattr(subscription.urllib.request, "urlopen", lambda *a, **k: FakeResponse())

    profiles = subscription.fetch_subscription_profiles("https://sub.example.com/sub/xyz")
    assert [p.name for p in profiles] == ["A", "B"]
    assert profiles[0].protocol == "vless"
    assert profiles[1].protocol == "trojan"


def test_fetch_subscription_profiles_parses_plain_list_body(monkeypatch):
    links = (
        "vless://11111111-2222-3333-4444-555555555555@example.com:443?encryption=none#A\n"
        "trojan://password@example.org:443?security=tls#B\n"
    )

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return links.encode()

    monkeypatch.setattr(subscription.urllib.request, "urlopen", lambda *a, **k: FakeResponse())

    profiles = subscription.fetch_subscription_profiles("https://sub.example.com/sub/xyz")
    assert [p.name for p in profiles] == ["A", "B"]


def test_fetch_subscription_profiles_raises_when_empty(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"nothing useful here"

    monkeypatch.setattr(subscription.urllib.request, "urlopen", lambda *a, **k: FakeResponse())

    with pytest.raises(subscription.SubscriptionError):
        subscription.fetch_subscription_profiles("https://sub.example.com/sub/xyz")


def test_fetch_subscription_profiles_wraps_network_errors(monkeypatch):
    def raise_error(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr(subscription.urllib.request, "urlopen", raise_error)

    with pytest.raises(subscription.SubscriptionError):
        subscription.fetch_subscription_profiles("https://sub.example.com/sub/xyz")
