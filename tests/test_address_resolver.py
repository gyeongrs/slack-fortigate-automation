from datetime import date

from fwgitops.address_resolver import (
    build_address_object,
    match_exact,
    parse_address_spec,
    propose_object,
    resolve_addresses,
)

_ADDR_OBJS = [
    {"name": "corp-clients", "type": "ipmask", "subnet": "10.20.0.0/16"},
    {"name": "app-web-server", "type": "ipmask", "subnet": "10.10.20.15/32"},
    {"name": "mgmt-host", "type": "ipmask", "subnet": "10.99.5.10/32"},
    {"name": "site-fqdn", "type": "fqdn", "fqdn": "example.com"},
]

_RULES = {
    "policy_naming": {
        "zone_map": {
            "core": "CR",
            "ch": "CH",
            "exco": "EX",
        }
    },
    "expiry": {"max_valid_days": 365, "default_valid_days": 90},
}


def test_object_name_passes_through():
    assert match_exact("corp-clients", _ADDR_OBJS) == "corp-clients"


def test_exact_cidr_matches_object():
    assert match_exact("10.99.5.10/32", _ADDR_OBJS) == "mgmt-host"


def test_bare_ip_is_treated_as_host():
    assert match_exact("10.10.20.15", _ADDR_OBJS) == "app-web-server"


def test_ip_inside_subnet_is_not_an_exact_match():
    assert match_exact("10.20.5.7", _ADDR_OBJS) is None


def test_garbage_token_is_no_match():
    assert match_exact("not-an-object", _ADDR_OBJS) is None


def test_propose_object_for_host_and_subnet():
    host = propose_object("10.30.1.2", set())
    assert host == {
        "name": "auto-10.30.1.2",
        "type": "ipmask",
        "subnet": "10.30.1.2/32",
        "comment": "Auto-created from Slack request",
    }


def test_build_address_object_with_zone():
    obj, errors = build_address_object(
        name="ch-app",
        address="10.51.10.15",
        prefix="32",
        zone="ch",
        center="dc1",
        expires_at=date(2026, 12, 31),
        comment="NETOPS-1",
        taken=set(),
        rules=_RULES,
    )
    assert errors == []
    assert obj == {
        "name": "ch-app",
        "type": "ipmask",
        "subnet": "10.51.10.15/32",
        "center": "dc1",
        "zone": "ch",
        "comment": "NETOPS-1",
        "expires_at": "2026-12-31",
    }


def test_build_address_object_rejects_unknown_zone():
    _, errors = build_address_object(
        name="x",
        address="10.1.1.1",
        prefix="32",
        zone="unknown",
        taken=set(),
        rules=_RULES,
    )
    assert any("zone" in e for e in errors)


def test_parse_address_spec():
    obj, errors = parse_address_spec(
        "partner=172.16.8.20 prefix=32 zone=exco expire=90 comment=NETOPS",
        set(),
        rules=_RULES,
    )
    assert errors == []
    assert obj["name"] == "partner"
    assert obj["subnet"] == "172.16.8.20/32"
    assert obj["zone"] == "exco"
    assert obj["expires_at"]


def test_resolve_without_autocreate_reports_unresolved():
    names, new, bad = resolve_addresses(["corp-clients", "8.8.8.8"], _ADDR_OBJS)
    assert names == ["corp-clients"]
    assert new == []
    assert bad == ["8.8.8.8"]


def test_bare_ip_not_autocreated_without_zone():
    names, new, bad = resolve_addresses(
        ["10.77.0.5/32"], _ADDR_OBJS, autocreate=True, rules=_RULES
    )
    assert names == []
    assert new == []
    assert len(bad) == 1
    assert "zone=" in bad[0]


def test_resolve_with_zone_spec_creates_object():
    names, new, bad = resolve_addresses(
        ["ch-host=10.77.0.5 prefix=32 zone=ch expire=90"],
        _ADDR_OBJS,
        "by tester",
        autocreate=True,
        rules=_RULES,
    )
    assert names == ["ch-host"]
    assert bad == []
    assert len(new) == 1
    assert new[0]["subnet"] == "10.77.0.5/32"
    assert new[0]["zone"] == "ch"


def test_named_address_requires_zone():
    names, new, bad = resolve_addresses(
        ["partner=172.16.8.20/32"], _ADDR_OBJS, autocreate=True, rules=_RULES
    )
    assert names == []
    assert new == []
    assert len(bad) == 1
    assert "zone=" in bad[0]
