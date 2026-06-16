from fwgitops.fortigate import FortiGateClient
from fwgitops.config import FortiGateConfig
from fwgitops.route_selector import Device, Route
from fwgitops.router_monitor import (
    collect_probe_ips,
    merge_routes,
    parse_lookup_entry,
    sync_device_routes,
)


def test_parse_lookup_entry_network():
    route = parse_lookup_entry(
        {
            "network": "10.52.10.0/24",
            "interface": "core-trust",
            "type": "connected",
            "gateway": "0.0.0.0",
        },
        "10.52.10.1",
    )
    assert route is not None
    assert route.dst == "10.52.10.0/24"
    assert route.interface == "core-trust"
    assert route.type == "connected"
    assert route.gateway is None


def test_parse_lookup_entry_fallback_dst():
    route = parse_lookup_entry({"interface": "lan", "type": "static"}, "10.1.2.3")
    assert route is not None
    assert route.dst == "10.1.2.3/32"
    assert route.interface == "lan"


def test_merge_routes_keeps_most_specific():
    routes = merge_routes(
        [
            Route(dst="10.0.0.0/8", interface="wan", type="static"),
            Route(dst="10.52.10.0/24", interface="wan", type="static"),
        ]
    )
    assert len(routes) == 2
    assert {r.dst for r in routes} == {"10.0.0.0/8", "10.52.10.0/24"}


def test_collect_probe_ips_merges_yaml_and_addresses():
    raw = {
        "route_probes": ["10.1.1.1"],
        "addresses": [{"subnet": "10.2.2.2/32"}],
    }
    probes = collect_probe_ips(raw)
    assert probes[0] == "10.1.1.1"
    assert "10.2.2.2" in probes


class _FakeClient(FortiGateClient):
    def __init__(self, mapping: dict[str, dict]) -> None:
        self._mapping = mapping
        self._cfg = FortiGateConfig(
            host="fake",
            api_token="x",
            verify_tls=True,
            vdom=None,
            dry_run=False,
        )

    def router_lookup(self, destination: str) -> list[dict]:
        row = self._mapping.get(destination)
        return [row] if row else []


def test_sync_device_routes_from_lookup():
    client = _FakeClient(
        {
            "10.52.10.1": {
                "network": "10.52.10.0/24",
                "interface": "core-trust",
                "type": "connected",
            },
            "10.54.10.1": {
                "network": "10.54.10.0/24",
                "interface": "core-untrust",
                "type": "static",
            },
        }
    )
    routes = sync_device_routes(client, ["10.52.10.1", "10.54.10.1"])
    assert len(routes) == 2
    ifaces = {r.interface for r in routes}
    assert ifaces == {"core-trust", "core-untrust"}


def test_device_lookup_prefers_live_client(monkeypatch):
    static = Device(
        name="fw",
        routes=[Route(dst="10.0.0.0/8", interface="wrong", type="static")],
    )
    fake = _FakeClient(
        {
            "10.52.10.1": {
                "network": "10.52.10.0/24",
                "interface": "core-trust",
                "type": "connected",
            }
        }
    )
    live = Device(
        name="fw",
        routes=static.routes,
        client=fake,
    )
    route = live.lookup("10.52.10.1")
    assert route is not None
    assert route.interface == "core-trust"
