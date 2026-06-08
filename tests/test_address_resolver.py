from fwgitops.address_resolver import (
    match_exact,
    propose_object,
    resolve_addresses,
)

_ADDR_OBJS = [
    {"name": "corp-clients", "type": "ipmask", "subnet": "10.20.0.0/16"},
    {"name": "app-web-server", "type": "ipmask", "subnet": "10.10.20.15/32"},
    {"name": "mgmt-host", "type": "ipmask", "subnet": "10.99.5.10/32"},
    {"name": "site-fqdn", "type": "fqdn", "fqdn": "example.com"},
]


def test_object_name_passes_through():
    assert match_exact("corp-clients", _ADDR_OBJS) == "corp-clients"


def test_exact_cidr_matches_object():
    assert match_exact("10.99.5.10/32", _ADDR_OBJS) == "mgmt-host"


def test_bare_ip_is_treated_as_host():
    assert match_exact("10.10.20.15", _ADDR_OBJS) == "app-web-server"


def test_ip_inside_subnet_is_not_an_exact_match():
    # We never silently widen to a broader existing object.
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
    net = propose_object("10.40.0.0/24", set())
    assert net["name"] == "auto-10.40.0.0_24"
    assert net["subnet"] == "10.40.0.0/24"


def test_propose_object_avoids_name_collision():
    obj = propose_object("10.30.1.2", {"auto-10.30.1.2"})
    assert obj["name"] == "auto-10.30.1.2-2"


def test_resolve_without_autocreate_reports_unresolved():
    names, new, bad = resolve_addresses(["corp-clients", "8.8.8.8"], _ADDR_OBJS)
    assert names == ["corp-clients"]
    assert new == []
    assert bad == ["8.8.8.8"]


def test_resolve_with_autocreate_makes_new_object():
    names, new, bad = resolve_addresses(
        ["corp-clients", "10.77.0.5/32"], _ADDR_OBJS, "by tester", autocreate=True
    )
    assert names == ["corp-clients", "auto-10.77.0.5"]
    assert bad == []
    assert len(new) == 1
    assert new[0]["subnet"] == "10.77.0.5/32"
    assert new[0]["comment"] == "by tester"


def test_repeated_new_ip_creates_only_one_object():
    names, new, bad = resolve_addresses(
        ["10.77.0.5", "10.77.0.5/32"], _ADDR_OBJS, autocreate=True
    )
    assert names == ["auto-10.77.0.5"]
    assert len(new) == 1


def test_invalid_token_still_unresolved_with_autocreate():
    names, new, bad = resolve_addresses(["nope!!"], _ADDR_OBJS, autocreate=True)
    assert names == []
    assert new == []
    assert bad == ["nope!!"]
