import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app import updater


def _fake_response(payload_json: bytes):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return payload_json

    return FakeResponse()


def test_check_for_update_finds_newer_release(monkeypatch):
    payload = (
        b'{"tag_name": "v1.2.0", "assets": ['
        b'{"name": "Nightjar-Setup.exe", "browser_download_url": "https://example.com/setup.exe"}'
        b"]}"
    )
    monkeypatch.setattr(
        updater.urllib.request, "urlopen", lambda *a, **k: _fake_response(payload)
    )

    info = updater.check_for_update("1.1.0")
    assert info is not None
    assert info.version == "1.2.0"
    assert info.download_url == "https://example.com/setup.exe"


def test_check_for_update_returns_none_when_up_to_date(monkeypatch):
    payload = b'{"tag_name": "v1.1.0", "assets": []}'
    monkeypatch.setattr(
        updater.urllib.request, "urlopen", lambda *a, **k: _fake_response(payload)
    )

    assert updater.check_for_update("1.1.0") is None
    assert updater.check_for_update("1.2.0") is None


def test_check_for_update_returns_none_without_exe_asset(monkeypatch):
    payload = b'{"tag_name": "v1.2.0", "assets": [{"name": "notes.txt"}]}'
    monkeypatch.setattr(
        updater.urllib.request, "urlopen", lambda *a, **k: _fake_response(payload)
    )

    assert updater.check_for_update("1.1.0") is None


def test_check_for_update_swallows_network_errors(monkeypatch):
    def raise_error(*a, **k):
        raise OSError("network down")

    monkeypatch.setattr(updater.urllib.request, "urlopen", raise_error)

    assert updater.check_for_update("1.1.0") is None


def test_download_installer_writes_file(tmp_path, monkeypatch):
    content = b"binary-content"

    class ChunkedFakeResponse:
        def __init__(self):
            self._remaining = content

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, size=-1):
            chunk, self._remaining = self._remaining[:size], self._remaining[size:]
            return chunk

    monkeypatch.setattr(
        updater.urllib.request, "urlopen", lambda *a, **k: ChunkedFakeResponse()
    )

    dest = tmp_path / "Nightjar-Setup-1.2.0.exe"
    updater.download_installer("https://example.com/setup.exe", dest)
    assert dest.read_bytes() == content


def test_download_installer_cleans_up_on_failure(tmp_path, monkeypatch):
    def raise_error(*a, **k):
        raise OSError("connection reset")

    monkeypatch.setattr(updater.urllib.request, "urlopen", raise_error)

    dest = tmp_path / "Nightjar-Setup-1.2.0.exe"
    with pytest.raises(updater.UpdateError):
        updater.download_installer("https://example.com/setup.exe", dest)
    assert not dest.exists()
