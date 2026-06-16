from fwgitops.policy_naming import (
    build_policy_name,
    device_prefix,
    parse_device_segments,
    request_summary_name,
)

_ADDR = [
    {"name": "src-host", "type": "ipmask", "subnet": "10.50.1.1/32"},
    {"name": "dst-host", "type": "ipmask", "subnet": "10.51.10.1/32"},
]

_NAMING = {
    "center_map": {"dc1": "D1", "dc2": "D2"},
    "zone_map": {"core": "cr", "ch": "ch"},
    "default_center_code": "00",
}


def test_parse_device_segments():
    assert parse_device_segments("dc1-core-fw") == ("dc1", "core")
    assert parse_device_segments("ch-fw") == (None, "ch")


def test_device_prefix_center_plus_zone():
    assert device_prefix("dc1-core-fw", _NAMING) == "D1cr"


def test_device_prefix_custom_codes():
    naming = {
        "center_map": {"dc1": "Centers"},
        "zone_map": {"core": "Security Zone"},
    }
    assert device_prefix("dc1-core-fw", naming) == "CentersSecurity Zone"


def test_device_prefix_zone_only_uses_default_center():
    assert device_prefix("ch-fw", _NAMING) == "00ch"


def test_build_policy_name_example():
    name = build_policy_name(
        "dc1-core-fw",
        ["src-host"],
        ["dst-host"],
        _ADDR,
        _NAMING,
    )
    assert name == "D1cr10.50.1.1>D1cr10.51.10.1"


def test_build_policy_name_from_raw_ip():
    name = build_policy_name(
        "dc1-core-fw",
        ["10.50.1.1/32"],
        ["10.51.10.1"],
        _ADDR,
        _NAMING,
    )
    assert name == "D1cr10.50.1.1>D1cr10.51.10.1"


def test_request_summary_name():
    assert request_summary_name(["src-host"], ["dst-host"], _ADDR) == "10.50.1.1>10.51.10.1"
