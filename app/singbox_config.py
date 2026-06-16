"""Build a sing-box JSON config (proxy outbound + tun inbound) from a profile dict.

Supports VLESS, Shadowsocks, Trojan, Hysteria2 and TUIC - build_outbound() dispatches
on profile.protocol."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .profile_parser import Profile

TUN_INTERFACE_NAME = "vless-client-tun"
CLASH_API_ADDRESS = "127.0.0.1:9090"


def _build_transport(profile: Profile) -> dict | None:
    if profile.network == "ws":
        return {
            "type": "ws",
            "path": profile.path or "/",
            "headers": {"Host": profile.host_header} if profile.host_header else {},
        }
    if profile.network == "grpc":
        return {
            "type": "grpc",
            "service_name": profile.service_name,
        }
    if profile.network == "http":
        return {
            "type": "http",
            "path": profile.path or "/",
            "host": [profile.host_header] if profile.host_header else [],
        }
    return None  # tcp: no transport block needed


def _build_tls(profile: Profile) -> dict | None:
    """Generic tls block for protocols that support reality/utls (vless, trojan)."""
    if profile.security == "none":
        return None

    tls: dict = {"enabled": True}
    if profile.sni:
        tls["server_name"] = profile.sni
    if profile.alpn:
        tls["alpn"] = profile.alpn

    if profile.fingerprint:
        tls["utls"] = {"enabled": True, "fingerprint": profile.fingerprint}

    if profile.security == "reality":
        if not profile.public_key:
            raise ValueError("Reality security requires a public_key (pbk)")
        tls["reality"] = {
            "enabled": True,
            "public_key": profile.public_key,
            "short_id": profile.short_id,
        }

    return tls


def _build_quic_tls(profile: Profile) -> dict:
    """Minimal tls block for QUIC-based protocols (hysteria2, tuic) - always
    enabled, no reality/utls support in sing-box for these."""
    tls: dict = {
        "enabled": True,
        "server_name": profile.sni or profile.host,
        "insecure": profile.insecure,
    }
    if profile.alpn:
        tls["alpn"] = profile.alpn
    return tls


def _build_vless_outbound(profile: Profile) -> dict:
    outbound: dict = {
        "type": "vless",
        "tag": "proxy",
        "server": profile.host,
        "server_port": profile.port,
        "uuid": profile.uuid,
        # Resolve the proxy server's own hostname directly, not through the tunnel
        # itself - the tunnel isn't up yet, so routing this through proxy-dns would deadlock.
        "domain_resolver": "direct-dns",
    }
    if profile.flow:
        outbound["flow"] = profile.flow

    tls = _build_tls(profile)
    if tls:
        outbound["tls"] = tls

    transport = _build_transport(profile)
    if transport:
        outbound["transport"] = transport

    return outbound


def _build_shadowsocks_outbound(profile: Profile) -> dict:
    return {
        "type": "shadowsocks",
        "tag": "proxy",
        "server": profile.host,
        "server_port": profile.port,
        "method": profile.method,
        "password": profile.password,
        "domain_resolver": "direct-dns",
    }


def _build_trojan_outbound(profile: Profile) -> dict:
    outbound: dict = {
        "type": "trojan",
        "tag": "proxy",
        "server": profile.host,
        "server_port": profile.port,
        "password": profile.password,
        "domain_resolver": "direct-dns",
    }

    tls = _build_tls(profile)
    if tls:
        outbound["tls"] = tls

    transport = _build_transport(profile)
    if transport:
        outbound["transport"] = transport

    return outbound


def _build_hysteria2_outbound(profile: Profile) -> dict:
    outbound: dict = {
        "type": "hysteria2",
        "tag": "proxy",
        "server": profile.host,
        "server_port": profile.port,
        "password": profile.password,
        "domain_resolver": "direct-dns",
        "tls": _build_quic_tls(profile),
    }
    if profile.obfs:
        outbound["obfs"] = {"type": profile.obfs, "password": profile.obfs_password}
    return outbound


def _build_tuic_outbound(profile: Profile) -> dict:
    return {
        "type": "tuic",
        "tag": "proxy",
        "server": profile.host,
        "server_port": profile.port,
        "uuid": profile.uuid,
        "password": profile.password,
        "congestion_control": profile.congestion_control or "bbr",
        "domain_resolver": "direct-dns",
        "tls": _build_quic_tls(profile),
    }


_OUTBOUND_BUILDERS = {
    "vless": _build_vless_outbound,
    "shadowsocks": _build_shadowsocks_outbound,
    "trojan": _build_trojan_outbound,
    "hysteria2": _build_hysteria2_outbound,
    "tuic": _build_tuic_outbound,
}


def build_outbound(profile: Profile) -> dict:
    builder = _OUTBOUND_BUILDERS.get(profile.protocol)
    if builder is None:
        raise ValueError(f"Unsupported protocol: {profile.protocol}")
    return builder(profile)


def build_config(profile: Profile, excluded_processes: list[str] | None = None) -> dict:
    """Full sing-box config: tun inbound, dns over the proxy, route avoiding loops.

    excluded_processes is a global (not per-profile) split-tunneling setting -
    these .exe names are routed direct, bypassing the VPN, regardless of which
    profile is active."""
    return {
        "log": {"level": "info", "timestamp": True},
        "dns": {
            "servers": [
                {"type": "udp", "tag": "proxy-dns", "server": "1.1.1.1", "detour": "proxy"},
                {"type": "local", "tag": "direct-dns"},
            ],
            "final": "proxy-dns",
            "strategy": "ipv4_only",
        },
        "inbounds": [
            {
                "type": "tun",
                "tag": "tun-in",
                "interface_name": TUN_INTERFACE_NAME,
                "address": ["172.19.0.1/30"],
                "mtu": 1500,
                "auto_route": True,
                "strict_route": True,
                "stack": "gvisor",
            }
        ],
        "outbounds": [
            build_outbound(profile),
            {"type": "direct", "tag": "direct"},
            {"type": "block", "tag": "block"},
        ],
        "route": {
            "auto_detect_interface": True,
            "default_domain_resolver": "direct-dns",
            "final": "proxy",
            "rules": _build_route_rules(excluded_processes),
        },
        "experimental": {
            "clash_api": {
                "external_controller": CLASH_API_ADDRESS,
            }
        },
    }


def _build_route_rules(excluded_processes: list[str] | None) -> list[dict]:
    rules = [
        {"action": "sniff"},
        {"protocol": "dns", "action": "hijack-dns"},
    ]
    if excluded_processes:
        rules.append(
            {
                "process_name": list(excluded_processes),
                "action": "route",
                "outbound": "direct",
            }
        )
    return rules


def build_blockall_config() -> dict:
    """Kill-switch config: keeps the TUN adapter (so the OS still routes through
    us) but drops every packet. Swapped in when the real tunnel crashes."""
    return {
        "log": {"level": "warning"},
        "inbounds": [
            {
                "type": "tun",
                "tag": "tun-in",
                "interface_name": TUN_INTERFACE_NAME,
                "address": ["172.19.0.1/30"],
                "mtu": 1500,
                "auto_route": True,
                "strict_route": True,
                "stack": "gvisor",
            }
        ],
        "outbounds": [{"type": "block", "tag": "block"}],
        "route": {
            "auto_detect_interface": True,
            "final": "block",
        },
    }


def write_blockall_config_file(directory: Path | None = None) -> Path:
    directory = directory or Path(tempfile.gettempdir())
    directory.mkdir(parents=True, exist_ok=True)
    config_path = directory / "singbox-blockall-config.json"
    config_path.write_text(json.dumps(build_blockall_config(), indent=2), encoding="utf-8")
    return config_path


def write_config_file(
    profile: Profile,
    directory: Path | None = None,
    excluded_processes: list[str] | None = None,
) -> Path:
    """Write the active config to a temp file and return its path.

    If the profile has a hand-edited raw_config (set via the JSON editor), it is
    used verbatim instead of generating one from the profile's fields (in that
    case the global split-tunneling list has no effect - it's not in that JSON)."""
    directory = directory or Path(tempfile.gettempdir())
    directory.mkdir(parents=True, exist_ok=True)
    config_path = directory / "singbox-config.json"

    if profile.raw_config.strip():
        config_text = profile.raw_config
    else:
        config_text = json.dumps(build_config(profile, excluded_processes), indent=2)

    config_path.write_text(config_text, encoding="utf-8")
    return config_path
