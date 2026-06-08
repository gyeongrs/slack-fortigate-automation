from fwgitops.models import Address, Policy
from fwgitops.route_selector import Device, Route, select_targets


def _addr(name: str, subnet: str) -> Address:
    return Address(name=name, type="ipmask", subnet=subnet)


_ADDR_INDEX = {
    a.name: a
    for a in [
        _addr("corp-clients", "10.20.0.0/16"),
        _addr("app-web-server", "10.10.20.15/32"),
        _addr("AWS", "10.52.10.1/32"),
        _addr("mgmt-host", "10.99.5.10/32"),
        _addr("partner-host", "172.16.8.20/32"),
    ]
}

_CORE_FW = Device(
    name="core-fw",
    routes=[
        Route(dst="10.20.0.0/16", interface="core-trust", type="connected"),
        Route(dst="10.99.5.10/32", interface="core-trust", type="static"),
        Route(dst="10.10.20.0/24", interface="dmz", type="connected"),
        Route(dst="10.52.10.1/32", interface="core-untrust", type="static"),
        Route(dst="0.0.0.0/0", interface="core-untrust", type="default"),
    ],
)

_INET_FW = Device(
    name="inet-fw",
    routes=[
        Route(dst="10.52.0.0/16", interface="inet-untrust", type="static"),
        Route(dst="10.56.0.0/16", interface="inet-untrust", type="static"),
        Route(dst="10.20.0.0/16", interface="inet-trust", type="static"),
        Route(dst="10.99.5.0/24", interface="inet-trust", type="static"),
        Route(dst="0.0.0.0/0", interface="inet-untrust", type="default"),
    ],
)

_MGT_FW = Device(
    name="mgt-fw",
    routes=[
        Route(dst="10.99.5.0/24", interface="mgmt-trust", type="connected"),
        Route(dst="10.52.10.0/24", interface="mgmt-untrust", type="connected"),
        Route(dst="10.20.0.0/16", interface="mgmt-untrust", type="static"),
        Route(dst="0.0.0.0/0", interface="mgmt-untrust", type="default"),
    ],
)

_EXCO_FW = Device(
    name="exco-fw",
    routes=[
        Route(dst="172.16.0.0/12", interface="exco-untrust", type="static"),
        Route(dst="10.0.0.0/8", interface="exco-trust", type="static"),
        Route(dst="0.0.0.0/0", interface="exco-untrust", type="default"),
    ],
)

_DEVICES = [_CORE_FW, _INET_FW, _MGT_FW, _EXCO_FW]


def _policy(name: str, src: str, dst: str) -> Policy:
    return Policy(
        name=name,
        srcintf=["x"],
        dstintf=["y"],
        srcaddr=[src],
        dstaddr=[dst],
        service=["HTTPS"],
    )


def test_corp_to_web_selects_core_fw():
    # Both endpoints are internal to core-fw (most specific match wins).
    pol = _policy("p", "corp-clients", "app-web-server")
    sel = select_targets(pol, _ADDR_INDEX, _DEVICES)
    assert sel.chosen is not None
    assert sel.chosen.device == "core-fw"
    assert sel.chosen.src_route.interface == "core-trust"
    assert sel.chosen.dst_route.interface == "dmz"


def test_corp_to_cloud_selects_core_fw_via_host_route():
    # core-fw has a /32 host route to the AWS server (more specific than
    # inet-fw's /16), so longest-prefix-match picks core-fw.
    pol = _policy("p", "corp-clients", "AWS")
    sel = select_targets(pol, _ADDR_INDEX, _DEVICES)
    assert sel.chosen is not None
    assert sel.chosen.device == "core-fw"
    assert sel.chosen.src_route.interface == "core-trust"
    assert sel.chosen.dst_route.interface == "core-untrust"


def test_corp_to_mgmt_selects_mgt_fw():
    # mgt-fw is the only one with a specific route into the management segment.
    pol = _policy("p", "corp-clients", "mgmt-host")
    sel = select_targets(pol, _ADDR_INDEX, _DEVICES)
    assert sel.chosen is not None
    assert sel.chosen.device == "mgt-fw"
    assert sel.chosen.src_route.interface == "mgmt-untrust"
    assert sel.chosen.dst_route.interface == "mgmt-trust"


def test_corp_to_partner_selects_exco_fw():
    # exco-fw transits internal (exco-trust) to partner (exco-untrust).
    pol = _policy("p", "corp-clients", "partner-host")
    sel = select_targets(pol, _ADDR_INDEX, _DEVICES)
    assert sel.chosen is not None
    assert sel.chosen.device == "exco-fw"
    assert sel.chosen.src_route.interface == "exco-trust"
    assert sel.chosen.dst_route.interface == "exco-untrust"


def test_aws_to_mgmt_transits_three_firewalls():
    # 10.52.10.1 -> 10.99.5.10 passes through inet-fw, core-fw and mgt-fw in
    # series; all three must be returned (exco-fw is not on the path).
    pol = _policy("p", "AWS", "mgmt-host")
    sel = select_targets(pol, _ADDR_INDEX, _DEVICES)
    devices = [m.device for m in sel.transit]
    assert set(devices) == {"core-fw", "inet-fw", "mgt-fw"}
    assert "exco-fw" not in devices
    assert devices[0] == "core-fw"  # most specific path first


def test_same_interface_is_not_transit():
    # Source and destination both resolve to the same interface -> not transit.
    dev = Device(
        name="solo",
        routes=[Route(dst="10.0.0.0/8", interface="lan", type="connected")],
    )
    idx = {
        "a": _addr("a", "10.1.0.0/16"),
        "b": _addr("b", "10.2.0.0/16"),
    }
    pol = _policy("p", "a", "b")
    sel = select_targets(pol, idx, [dev])
    assert sel.chosen is None
    assert sel.matches[0].is_transit is False
