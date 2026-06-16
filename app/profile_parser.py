"""Parse share links for VLESS, Shadowsocks, Trojan, Hysteria2 and TUIC into a
common Profile, auto-detected by URI scheme."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from urllib.parse import parse_qs, unquote, urlparse


class ProfileParseError(ValueError):
    pass


@dataclass
class Profile:
    name: str
    protocol: str = "vless"  # vless | shadowsocks | trojan | hysteria2 | tuic
    host: str = ""
    port: int = 0
    uuid: str = ""  # vless, tuic
    password: str = ""  # shadowsocks, trojan, hysteria2, tuic
    method: str = ""  # shadowsocks cipher
    encryption: str = "none"  # vless
    security: str = "none"  # none | tls | reality (vless, trojan)
    network: str = "tcp"  # tcp | ws | grpc | http (vless, trojan)
    flow: str = ""  # vless
    sni: str = ""
    fingerprint: str = ""
    public_key: str = ""  # reality (vless)
    short_id: str = ""  # reality (vless)
    spider_x: str = ""  # reality (vless)
    alpn: list[str] = field(default_factory=list)
    path: str = ""
    host_header: str = ""
    service_name: str = ""
    obfs: str = ""  # hysteria2
    obfs_password: str = ""  # hysteria2
    insecure: bool = False  # hysteria2, tuic: skip certificate verification
    congestion_control: str = "bbr"  # tuic
    raw_config: str = ""  # hand-edited sing-box JSON; overrides all fields above when set

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "protocol": self.protocol,
            "host": self.host,
            "port": self.port,
            "uuid": self.uuid,
            "password": self.password,
            "method": self.method,
            "encryption": self.encryption,
            "security": self.security,
            "network": self.network,
            "flow": self.flow,
            "sni": self.sni,
            "fingerprint": self.fingerprint,
            "public_key": self.public_key,
            "short_id": self.short_id,
            "spider_x": self.spider_x,
            "alpn": self.alpn,
            "path": self.path,
            "host_header": self.host_header,
            "service_name": self.service_name,
            "obfs": self.obfs,
            "obfs_password": self.obfs_password,
            "insecure": self.insecure,
            "congestion_control": self.congestion_control,
            "raw_config": self.raw_config,
        }


def _b64_decode_maybe(text: str) -> str:
    """Try base64 (with padding correction); fall back to the original text
    if it isn't valid base64 - some panels leave userinfo unencoded."""
    padded = text + "=" * (-len(text) % 4)
    try:
        return base64.urlsafe_b64decode(padded).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        try:
            return base64.b64decode(padded).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return text


def _split_remark(uri: str) -> tuple[str, str]:
    if "#" in uri:
        body, frag = uri.split("#", 1)
        return body, unquote(frag)
    return uri, ""


def parse_vless_uri(uri: str) -> Profile:
    """Parse a single vless:// URI. Raises ProfileParseError on malformed input."""
    uri = uri.strip()
    if not uri.lower().startswith("vless://"):
        raise ProfileParseError("Not a vless:// link")

    parsed = urlparse(uri)
    if not parsed.username or not parsed.hostname or not parsed.port:
        raise ProfileParseError("Link is missing uuid, host or port")

    params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    remark = unquote(parsed.fragment) if parsed.fragment else f"{parsed.hostname}:{parsed.port}"

    alpn_raw = params.get("alpn", "")
    alpn = [a for a in alpn_raw.split(",") if a] if alpn_raw else []

    return Profile(
        name=remark,
        protocol="vless",
        uuid=parsed.username,
        host=parsed.hostname,
        port=parsed.port,
        encryption=params.get("encryption", "none"),
        security=params.get("security", "none"),
        network=params.get("type", "tcp"),
        flow=params.get("flow", ""),
        sni=params.get("sni", ""),
        fingerprint=params.get("fp", ""),
        public_key=params.get("pbk", ""),
        short_id=params.get("sid", ""),
        spider_x=unquote(params.get("spx", "")),
        alpn=alpn,
        path=unquote(params.get("path", "")),
        host_header=params.get("host", ""),
        service_name=unquote(params.get("serviceName", "")),
    )


def parse_shadowsocks_uri(uri: str) -> Profile:
    """Parse ss:// (SIP002: ss://BASE64(method:password)@host:port?...#remark,
    with a fallback for the legacy fully-base64-encoded form)."""
    uri = uri.strip()
    if not uri.lower().startswith("ss://"):
        raise ProfileParseError("Not an ss:// link")

    body, remark = _split_remark(uri[len("ss://") :])
    body, _, query = body.partition("?")
    params = {k: v[0] for k, v in parse_qs(query).items()}

    if "@" in body:
        userinfo, hostport = body.rsplit("@", 1)
        userinfo = _b64_decode_maybe(userinfo)
    else:
        decoded = _b64_decode_maybe(body)
        if "@" not in decoded:
            raise ProfileParseError("Malformed ss:// link")
        userinfo, hostport = decoded.rsplit("@", 1)

    method, _, password = userinfo.partition(":")
    if not method or not password:
        raise ProfileParseError("ss:// link is missing method or password")

    host, _, port_str = hostport.rpartition(":")
    if not host or not port_str.isdigit():
        raise ProfileParseError("ss:// link is missing host or port")

    return Profile(
        name=remark or f"{host}:{port_str}",
        protocol="shadowsocks",
        host=host,
        port=int(port_str),
        method=method,
        password=password,
    )


def parse_trojan_uri(uri: str) -> Profile:
    """Parse trojan://password@host:port?security=tls&sni=...&type=...#remark."""
    uri = uri.strip()
    if not uri.lower().startswith("trojan://"):
        raise ProfileParseError("Not a trojan:// link")

    parsed = urlparse(uri)
    if not parsed.username or not parsed.hostname or not parsed.port:
        raise ProfileParseError("Link is missing password, host or port")

    params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    remark = unquote(parsed.fragment) if parsed.fragment else f"{parsed.hostname}:{parsed.port}"

    alpn_raw = params.get("alpn", "")
    alpn = [a for a in alpn_raw.split(",") if a] if alpn_raw else []

    return Profile(
        name=remark,
        protocol="trojan",
        host=parsed.hostname,
        port=parsed.port,
        password=unquote(parsed.username),
        security=params.get("security", "tls"),
        network=params.get("type", "tcp"),
        sni=params.get("sni", ""),
        fingerprint=params.get("fp", ""),
        alpn=alpn,
        path=unquote(params.get("path", "")),
        host_header=params.get("host", ""),
        service_name=unquote(params.get("serviceName", "")),
    )


def parse_hysteria2_uri(uri: str) -> Profile:
    """Parse hysteria2:// (or hy2://) password@host:port?insecure=1&sni=...
    &obfs=salamander&obfs-password=...#remark."""
    uri = uri.strip()
    lowered = uri.lower()
    if lowered.startswith("hysteria2://"):
        prefix_len = len("hysteria2://")
    elif lowered.startswith("hy2://"):
        prefix_len = len("hy2://")
    else:
        raise ProfileParseError("Not a hysteria2:// or hy2:// link")

    parsed = urlparse(uri)
    if not parsed.username or not parsed.hostname or not parsed.port:
        raise ProfileParseError("Link is missing password, host or port")

    params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    remark = unquote(parsed.fragment) if parsed.fragment else f"{parsed.hostname}:{parsed.port}"
    insecure = params.get("insecure", "0") in ("1", "true", "True")

    return Profile(
        name=remark,
        protocol="hysteria2",
        host=parsed.hostname,
        port=parsed.port,
        password=unquote(parsed.username),
        sni=params.get("sni", ""),
        obfs=params.get("obfs", ""),
        obfs_password=params.get("obfs-password", ""),
        insecure=insecure,
    )


def parse_tuic_uri(uri: str) -> Profile:
    """Parse tuic://uuid:password@host:port?congestion_control=bbr&alpn=h3
    &sni=...&allow_insecure=1#remark."""
    uri = uri.strip()
    if not uri.lower().startswith("tuic://"):
        raise ProfileParseError("Not a tuic:// link")

    parsed = urlparse(uri)
    if not parsed.username or not parsed.hostname or not parsed.port:
        raise ProfileParseError("Link is missing uuid/password, host or port")

    uuid_part = parsed.username
    password_part = unquote(parsed.password) if parsed.password else ""

    params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    remark = unquote(parsed.fragment) if parsed.fragment else f"{parsed.hostname}:{parsed.port}"
    insecure = params.get("allow_insecure", "0") in ("1", "true", "True")

    alpn_raw = params.get("alpn", "")
    alpn = [a for a in alpn_raw.split(",") if a] if alpn_raw else []

    return Profile(
        name=remark,
        protocol="tuic",
        host=parsed.hostname,
        port=parsed.port,
        uuid=uuid_part,
        password=password_part,
        sni=params.get("sni", ""),
        alpn=alpn,
        congestion_control=params.get("congestion_control", "bbr"),
        insecure=insecure,
    )


_PARSERS_BY_PREFIX = [
    ("vless://", parse_vless_uri),
    ("ss://", parse_shadowsocks_uri),
    ("trojan://", parse_trojan_uri),
    ("hysteria2://", parse_hysteria2_uri),
    ("hy2://", parse_hysteria2_uri),
    ("tuic://", parse_tuic_uri),
]


SUPPORTED_SCHEMES = tuple(prefix for prefix, _parser in _PARSERS_BY_PREFIX)


def looks_like_profile_uri(text: str) -> bool:
    return text.strip().lower().startswith(SUPPORTED_SCHEMES)


def parse_profile_uri(uri: str) -> Profile:
    """Auto-detect the protocol by URI scheme and parse accordingly."""
    stripped = uri.strip().lower()
    for prefix, parser in _PARSERS_BY_PREFIX:
        if stripped.startswith(prefix):
            return parser(uri)
    raise ProfileParseError("Unsupported or unrecognized link format")
