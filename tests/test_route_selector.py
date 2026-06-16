from fwgitops.models import Address, Policy
from fwgitops.route_selector import Device, Route, load_devices, select_targets


def _addr(name: str, subnet: str) -> Address:
    return Address(name=name, type="ipmask", subnet=subnet)


_DEVICES = load_devices()

_ADDR_INDEX = {
    a.name: a
    for a in [
        _addr("aws-host", "10.52.10.1/32"),
        _addr("dmz-host", "10.54.10.1/32"),
        _addr("partner-host", "10.53.10.1/32"),
        _addr("ch-host", "10.51.10.1/32"),
        _addr("svr-host", "10.56.10.1/32"),
        _addr("cc-host", "10.58.10.1/32"),
    ]
}


def _policy(name: str, src: str, dst: str) -> Policy:
    return Policy(
        name=name,
        srcintf=["x"],
        dstintf=["y"],
        srcaddr=[src],
        dstaddr=[dst],
        service=["HTTPS"],
    )


def test_inventory_includes_zone_firewalls():
    names = {d.name for d in _DEVICES}
    assert names >= {
        "dc1-core-fw",
        "dc1-inet-fw",
        "dc1-mgt-fw",
        "dc1-exco-fw",
        "dc1-ch-fw",
        "dc1-svr-fw",
        "dc1-vdi-fw",
        "dc1-dmz-fw",
        "dc1-cc-fw",
    }


def test_aws_to_dmz_transits_three_firewalls():
    pol = _policy("p", "aws-host", "dmz-host")
    sel = select_targets(pol, _ADDR_INDEX, _DEVICES)
    devices = {m.device for m in sel.transit}
    assert devices == {"dc1-core-fw", "dc1-inet-fw", "dc1-mgt-fw"}


def test_core_fw_transit_interfaces_for_aws_to_dmz():
    pol = _policy("p", "aws-host", "dmz-host")
    sel = select_targets(pol, _ADDR_INDEX, _DEVICES)
    core = next(m for m in sel.transit if m.device == "dc1-core-fw")
    assert core.src_route.interface == "core-trust"
    assert core.dst_route.interface == "core-untrust"


def test_aws_to_partner_transits_exco_fw():
    pol = _policy("p", "aws-host", "partner-host")
    sel = select_targets(pol, _ADDR_INDEX, _DEVICES)
    exco = next(m for m in sel.transit if m.device == "dc1-exco-fw")
    assert exco.src_route.interface == "exco-trust"
    assert exco.dst_route.interface == "exco-untrust"


def test_ch_to_svr_transits_zone_firewalls():
    pol = _policy("p", "ch-host", "svr-host")
    sel = select_targets(pol, _ADDR_INDEX, _DEVICES)
    devices = {m.device for m in sel.transit}
    assert devices == {"dc1-ch-fw", "dc1-svr-fw"}


def test_ch_to_cc_transits_zone_firewalls():
    pol = _policy("p", "ch-host", "cc-host")
    sel = select_targets(pol, _ADDR_INDEX, _DEVICES)
    devices = {m.device for m in sel.transit}
    assert devices == {"dc1-ch-fw", "dc1-cc-fw"}


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
