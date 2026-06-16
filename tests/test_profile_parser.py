import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.profile_parser import (
    ProfileParseError,
    looks_like_profile_uri,
    parse_hysteria2_uri,
    parse_profile_uri,
    parse_shadowsocks_uri,
    parse_trojan_uri,
    parse_tuic_uri,
    parse_vless_uri,
)


def test_reality_vision_tcp():
    uri = (
        "vless://11111111-2222-3333-4444-555555555555@example.com:443"
        "?encryption=none&security=reality&type=tcp&flow=xtls-rprx-vision"
        "&sni=www.microsoft.com&fp=chrome&pbk=PUBKEY123&sid=ab12"
        "#My%20Server"
    )
    profile = parse_vless_uri(uri)
    assert profile.protocol == "vless"
    assert profile.uuid == "11111111-2222-3333-4444-555555555555"
    assert profile.host == "example.com"
    assert profile.port == 443
    assert profile.security == "reality"
    assert profile.network == "tcp"
    assert profile.flow == "xtls-rprx-vision"
    assert profile.sni == "www.microsoft.com"
    assert profile.fingerprint == "chrome"
    assert profile.public_key == "PUBKEY123"
    assert profile.short_id == "ab12"
    assert profile.name == "My Server"


def test_tls_websocket():
    uri = (
        "vless://aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee@vpn.example.org:8443"
        "?encryption=none&security=tls&type=ws&sni=vpn.example.org"
        "&path=%2Fws-path&host=vpn.example.org#WS%20Profile"
    )
    profile = parse_vless_uri(uri)
    assert profile.security == "tls"
    assert profile.network == "ws"
    assert profile.path == "/ws-path"
    assert profile.host_header == "vpn.example.org"
    assert profile.name == "WS Profile"


def test_tls_grpc():
    uri = (
        "vless://aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee@grpc.example.org:443"
        "?encryption=none&security=tls&type=grpc&sni=grpc.example.org"
        "&serviceName=mygrpc#GRPC%20Profile"
    )
    profile = parse_vless_uri(uri)
    assert profile.network == "grpc"
    assert profile.service_name == "mygrpc"


def test_missing_uuid_raises():
    try:
        parse_vless_uri("vless://@example.com:443?security=none")
        assert False, "expected ProfileParseError"
    except ProfileParseError:
        pass


def test_not_a_vless_link_raises():
    try:
        parse_vless_uri("https://example.com")
        assert False, "expected ProfileParseError"
    except ProfileParseError:
        pass


def test_shadowsocks_sip002():
    # base64("aes-256-gcm:Sup3rSecret")
    uri = "ss://YWVzLTI1Ni1nY206U3VwM3JTZWNyZXQ@ss.example.com:8388#SS%20Profile"
    profile = parse_shadowsocks_uri(uri)
    assert profile.protocol == "shadowsocks"
    assert profile.method == "aes-256-gcm"
    assert profile.password == "Sup3rSecret"
    assert profile.host == "ss.example.com"
    assert profile.port == 8388
    assert profile.name == "SS Profile"


def test_shadowsocks_legacy_full_base64():
    import base64

    encoded = base64.urlsafe_b64encode(
        b"chacha20-ietf-poly1305:legacypass@legacy.example.com:9000"
    ).decode().rstrip("=")
    uri = f"ss://{encoded}#Legacy"
    profile = parse_shadowsocks_uri(uri)
    assert profile.method == "chacha20-ietf-poly1305"
    assert profile.password == "legacypass"
    assert profile.host == "legacy.example.com"
    assert profile.port == 9000


def test_trojan_basic():
    uri = (
        "trojan://mypassword@trojan.example.com:443"
        "?security=tls&sni=trojan.example.com&type=tcp#Trojan%20Profile"
    )
    profile = parse_trojan_uri(uri)
    assert profile.protocol == "trojan"
    assert profile.password == "mypassword"
    assert profile.host == "trojan.example.com"
    assert profile.port == 443
    assert profile.security == "tls"
    assert profile.sni == "trojan.example.com"
    assert profile.name == "Trojan Profile"


def test_hysteria2_basic():
    uri = (
        "hysteria2://hy2pass@hy.example.com:443"
        "?insecure=1&sni=hy.example.com&obfs=salamander&obfs-password=obfspass#HY2"
    )
    profile = parse_hysteria2_uri(uri)
    assert profile.protocol == "hysteria2"
    assert profile.password == "hy2pass"
    assert profile.host == "hy.example.com"
    assert profile.port == 443
    assert profile.insecure is True
    assert profile.sni == "hy.example.com"
    assert profile.obfs == "salamander"
    assert profile.obfs_password == "obfspass"
    assert profile.name == "HY2"


def test_hy2_alias_scheme():
    uri = "hy2://hy2pass@hy.example.com:443?sni=hy.example.com#HY2Alias"
    profile = parse_hysteria2_uri(uri)
    assert profile.protocol == "hysteria2"
    assert profile.name == "HY2Alias"


def test_tuic_basic():
    uri = (
        "tuic://11111111-2222-3333-4444-555555555555:tuicpass@tuic.example.com:443"
        "?congestion_control=bbr&alpn=h3&sni=tuic.example.com&allow_insecure=1#TUIC"
    )
    profile = parse_tuic_uri(uri)
    assert profile.protocol == "tuic"
    assert profile.uuid == "11111111-2222-3333-4444-555555555555"
    assert profile.password == "tuicpass"
    assert profile.host == "tuic.example.com"
    assert profile.port == 443
    assert profile.congestion_control == "bbr"
    assert profile.alpn == ["h3"]
    assert profile.insecure is True
    assert profile.name == "TUIC"


def test_dispatcher_auto_detects_protocol():
    links = {
        "vless": "vless://11111111-2222-3333-4444-555555555555@h:443?security=none#x",
        "shadowsocks": "ss://YWVzLTI1Ni1nY206U3VwM3JTZWNyZXQ@h:8388#x",
        "trojan": "trojan://pass@h:443#x",
        "hysteria2": "hysteria2://pass@h:443#x",
        "tuic": "tuic://uuid:pass@h:443#x",
    }
    for expected_protocol, link in links.items():
        profile = parse_profile_uri(link)
        assert profile.protocol == expected_protocol, link


def test_dispatcher_unsupported_scheme_raises():
    try:
        parse_profile_uri("wireguard://something")
        assert False, "expected ProfileParseError"
    except ProfileParseError:
        pass


def test_looks_like_profile_uri():
    assert looks_like_profile_uri("vless://x@y:443")
    assert looks_like_profile_uri("ss://x@y:443")
    assert looks_like_profile_uri("  trojan://x@y:443  ")
    assert not looks_like_profile_uri("https://example.com")
    assert not looks_like_profile_uri("just some text")


if __name__ == "__main__":
    test_reality_vision_tcp()
    test_tls_websocket()
    test_tls_grpc()
    test_missing_uuid_raises()
    test_not_a_vless_link_raises()
    test_shadowsocks_sip002()
    test_shadowsocks_legacy_full_base64()
    test_trojan_basic()
    test_hysteria2_basic()
    test_hy2_alias_scheme()
    test_tuic_basic()
    test_dispatcher_auto_detects_protocol()
    test_dispatcher_unsupported_scheme_raises()
    test_looks_like_profile_uri()
    print("All tests passed.")
