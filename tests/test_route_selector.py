from fwgitops.models import Address, Policy
from fwgitops.route_selector import Device, Route, select_targets


def _addr(name: str, subnet: str) -> Address:
    return Address(name=name, type="ipmask", subnet=subnet)


_ADDR_INDEX = {
    a.name: a
    for a in [
        _addr("aws-host", "10.52.10.1/32"),
        _addr("dmz-host", "10.54.10.1/32"),
        _addr("partner-host", "10.53.10.1/32"),
    ]
}

_CORE_FW = Device(
    name="core-fw",
    routes=[
        Route(dst="10.55.10.0/24", interface="core-trust", type="static"),
        Route(dst="10.55.20.0/24", interface="core-trust", type="static"),
        Route(dst="10.55.30.0/24", interface="core-trust", type="static"),
        Route(dst="10.55.40.0/24", interface="core-trust", type="static"),
        Route(dst="10.55.50.0/24", interface="core-trust", type="static"),
        Route(dst="10.55.60.0/24", interface="core-trust", type="static"),
        Route(dst="10.52.10.0/24", interface="core-trust", type="static"),
        Route(dst="10.52.20.0/24", interface="core-trust", type="static"),
        Route(dst="10.52.30.0/24", interface="core-trust", type="static"),
        Route(dst="10.52.40.0/24", interface="core-trust", type="static"),
        Route(dst="10.52.50.0/24", interface="core-trust", type="static"),
        Route(dst="10.52.60.0/24", interface="core-trust", type="static"),
        Route(dst="10.54.10.0/24", interface="core-untrust", type="static"),
        Route(dst="10.54.20.0/24", interface="core-untrust", type="static"),
        Route(dst="10.54.30.0/24", interface="core-untrust", type="static"),
        Route(dst="10.54.40.0/24", interface="core-untrust", type="static"),
        Route(dst="10.54.50.0/24", interface="core-untrust", type="static"),
        Route(dst="10.54.60.0/24", interface="core-untrust", type="static"),
        Route(dst="10.53.10.0/24", interface="core-untrust", type="static"),
        Route(dst="10.53.20.0/24", interface="core-untrust", type="static"),
        Route(dst="10.53.30.0/24", interface="core-untrust", type="static"),
        Route(dst="10.53.40.0/24", interface="core-untrust", type="static"),
        Route(dst="10.53.50.0/24", interface="core-untrust", type="static"),
        Route(dst="10.53.60.0/24", interface="core-untrust", type="static"),
    ],
)

_INET_FW = Device(
    name="inet-fw",
    routes=[
        Route(dst="10.52.0.0/16", interface="inet-trust", type="static"),
        Route(dst="10.53.0.0/16", interface="inet-trust", type="static"),
        Route(dst="10.55.0.0/16", interface="inet-trust", type="static"),
        Route(dst="10.54.10.0/24", interface="inet-untrust", type="static"),
        Route(dst="10.54.20.0/24", interface="inet-untrust", type="static"),
        Route(dst="10.54.30.0/24", interface="inet-untrust", type="static"),
        Route(dst="10.54.40.0/24", interface="inet-untrust", type="static"),
        Route(dst="10.54.50.0/24", interface="inet-untrust", type="static"),
        Route(dst="10.54.60.0/24", interface="inet-untrust", type="static"),
    ],
)

_MGT_FW = Device(
    name="mgt-fw",
    routes=[
        Route(dst="10.54.0.0/16", interface="mgt-untrust", type="static"),
        Route(dst="10.53.0.0/16", interface="mgt-untrust", type="static"),
        Route(dst="10.55.0.0/16", interface="mgt-untrust", type="static"),
        Route(dst="10.52.10.0/24", interface="mgt-trust", type="static"),
        Route(dst="10.52.20.0/24", interface="mgt-trust", type="static"),
        Route(dst="10.52.30.0/24", interface="mgt-trust", type="static"),
        Route(dst="10.52.40.0/24", interface="mgt-trust", type="static"),
        Route(dst="10.52.50.0/24", interface="mgt-trust", type="static"),
        Route(dst="10.52.60.0/24", interface="mgt-trust", type="static"),
    ],
)

_EXCO_FW = Device(
    name="exco-fw",
    routes=[
        Route(dst="10.52.0.0/16", interface="exco-trust", type="static"),
        Route(dst="10.54.0.0/16", interface="exco-trust", type="static"),
        Route(dst="10.55.0.0/16", interface="exco-trust", type="static"),
        Route(dst="10.53.10.0/24", interface="exco-untrust", type="static"),
        Route(dst="10.53.20.0/24", interface="exco-untrust", type="static"),
        Route(dst="10.53.30.0/24", interface="exco-untrust", type="static"),
        Route(dst="10.53.40.0/24", interface="exco-untrust", type="static"),
        Route(dst="10.53.50.0/24", interface="exco-untrust", type="static"),
        Route(dst="10.53.60.0/24", interface="exco-untrust", type="static"),
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


def test_aws_to_dmz_transits_three_firewalls():
    # 10.52.10.1 -> 10.54.10.1 passes through core-fw, inet-fw and mgt-fw.
    pol = _policy("p", "aws-host", "dmz-host")
    sel = select_targets(pol, _ADDR_INDEX, _DEVICES)
    devices = {m.device for m in sel.transit}
    assert devices == {"core-fw", "inet-fw", "mgt-fw"}
    assert "exco-fw" not in devices


def test_core_fw_transit_interfaces_for_aws_to_dmz():
    pol = _policy("p", "aws-host", "dmz-host")
    sel = select_targets(pol, _ADDR_INDEX, _DEVICES)
    core = next(m for m in sel.transit if m.device == "core-fw")
    assert core.src_route.interface == "core-trust"
    assert core.dst_route.interface == "core-untrust"


def test_aws_to_partner_transits_exco_fw():
    # 10.52.10.1 -> 10.53.10.1: exco-fw sees exco-trust -> exco-untrust.
    pol = _policy("p", "aws-host", "partner-host")
    sel = select_targets(pol, _ADDR_INDEX, _DEVICES)
    exco = next((m for m in sel.transit if m.device == "exco-fw"), None)
    assert exco is not None
    assert exco.src_route.interface == "exco-trust"
    assert exco.dst_route.interface == "exco-untrust"


def test_same_interface_is_not_transit():
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
