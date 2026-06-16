from fwgitops.policy_naming import (
    address_flow_segment,
    build_policy_name,
    device_prefix,
    parse_device_segments,
    request_summary_name,
)

_ADDR = [
    {
        "name": "NEF-10.54.20.20",
        "type": "ipmask",
        "subnet": "10.54.20.20/32",
        "center": "dc1",
        "zone": "inet",
    },
    {
        "name": "Azure-10.56.10.1",
        "type": "ipmask",
        "subnet": "10.56.10.1/32",
        "center": "dc1",
        "zone": "svr",
    },
]

_NAMING = {
    "center_map": {"dc1": "D1", "dc2": "D2"},
    "zone_map": {"core": "CR", "inet": "IN", "ch": "CH", "svr": "SV"},
    "default_center_code": "00",
}


def test_parse_device_segments():
    assert parse_device_segments("dc1-core-fw") == ("dc1", "core")
    assert parse_device_segments("ch-fw") == (None, "ch")


def test_device_prefix_center_plus_zone():
    assert device_prefix("dc1-core-fw", _NAMING) == "D1CR"


def test_address_flow_segment():
    assert address_flow_segment("NEF-10.54.20.20", _ADDR) == "dc1inet-10.54.20.20"
    assert address_flow_segment("Azure-10.56.10.1", _ADDR) == "dc1svr-10.56.10.1"


def test_build_policy_name_flow_based():
    name = build_policy_name(
        "dc1-inet-fw",
        ["NEF-10.54.20.20"],
        ["Azure-10.56.10.1"],
        _ADDR,
        _NAMING,
    )
    assert name == "dc1inet-10.54.20.20>dc1svr-10.56.10"


def test_build_policy_name_same_on_every_transit_fw():
    inet = build_policy_name(
        "dc1-inet-fw",
        ["NEF-10.54.20.20"],
        ["Azure-10.56.10.1"],
        _ADDR,
        _NAMING,
    )
    svr = build_policy_name(
        "dc1-svr-fw",
        ["NEF-10.54.20.20"],
        ["Azure-10.56.10.1"],
        _ADDR,
        _NAMING,
    )
    assert inet == svr == "dc1inet-10.54.20.20>dc1svr-10.56.10"


def test_request_summary_name_matches_policy_name():
    assert (
        request_summary_name(
            ["NEF-10.54.20.20"],
            ["Azure-10.56.10.1"],
            _ADDR,
            _NAMING,
        )
        == "dc1inet-10.54.20.20>dc1svr-10.56.10"
    )


def test_address_flow_segment_without_labels_uses_ip_only():
    assert address_flow_segment("unknown-host", _ADDR) == "unknown-host"
