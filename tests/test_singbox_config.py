import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.profile_parser import Profile
from app.singbox_config import build_blockall_config, build_config

PROFILE = Profile(
    name="test",
    protocol="vless",
    host="example.com",
    port=443,
    uuid="11111111-2222-3333-4444-555555555555",
)


def test_exclude_mode_routes_domains_direct():
    config = build_config(
        PROFILE, split_tunnel_mode="exclude", excluded_domains=["youtube.com", "twitter.com"]
    )
    domain_rules = [r for r in config["route"]["rules"] if "domain_suffix" in r]
    assert domain_rules == [
        {
            "domain_suffix": ["youtube.com", "twitter.com"],
            "action": "route",
            "outbound": "direct",
        }
    ]
    assert config["route"]["final"] == "proxy"
    # Everything defaults through the tunnel's DNS in exclude mode, even for
    # domains that end up routed direct - only route.rules diverts them.
    assert config["dns"]["rules"] == []


def test_include_mode_routes_domains_through_proxy():
    config = build_config(
        PROFILE, split_tunnel_mode="include", excluded_domains=["youtube.com"]
    )
    domain_route_rules = [r for r in config["route"]["rules"] if "domain_suffix" in r]
    assert domain_route_rules == [
        {"domain_suffix": ["youtube.com"], "action": "route", "outbound": "proxy"}
    ]
    assert config["route"]["final"] == "direct"

    domain_dns_rules = [r for r in config["dns"]["rules"] if "domain_suffix" in r]
    assert domain_dns_rules == [{"domain_suffix": ["youtube.com"], "server": "proxy-dns"}]
    assert config["dns"]["final"] == "direct-dns"


def test_processes_and_domains_are_separate_rules_not_anded_together():
    config = build_config(
        PROFILE,
        split_tunnel_mode="include",
        excluded_processes=["Spotify.exe"],
        excluded_domains=["youtube.com"],
    )
    rules = config["route"]["rules"]
    process_rules = [r for r in rules if "process_name" in r]
    domain_rules = [r for r in rules if "domain_suffix" in r]
    assert process_rules == [
        {"process_name": ["Spotify.exe"], "action": "route", "outbound": "proxy"}
    ]
    assert domain_rules == [
        {"domain_suffix": ["youtube.com"], "action": "route", "outbound": "proxy"}
    ]


def test_no_domains_means_no_domain_rules():
    config = build_config(PROFILE, split_tunnel_mode="exclude", excluded_domains=None)
    assert all("domain_suffix" not in r for r in config["route"]["rules"])
    assert all("domain_suffix" not in r for r in config["dns"]["rules"])


def test_blockall_include_mode_blocks_listed_domains():
    config = build_blockall_config(split_tunnel_mode="include", excluded_domains=["youtube.com"])
    domain_rules = [r for r in config["route"]["rules"] if "domain_suffix" in r]
    assert domain_rules == [
        {"domain_suffix": ["youtube.com"], "action": "route", "outbound": "block"}
    ]
    assert config["route"]["final"] == "direct"


def test_blockall_exclude_mode_ignores_domains_and_blocks_everything():
    config = build_blockall_config(split_tunnel_mode="exclude", excluded_domains=["youtube.com"])
    assert config["route"]["final"] == "block"
    assert "rules" not in config["route"]
