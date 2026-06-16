"""FortiGate monitor/router/lookup integration and devices.yaml route sync."""

from __future__ import annotations

import ipaddress
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .config import REPO_ROOT
from .config import FortiGateConfig
from .fortigate import FortiGateClient, FortiGateError
from .route_selector import DEVICES_FILE, Device, Route, devices_from_dict, load_devices

# Representative IPs probed via GET /api/v2/monitor/router/lookup?destination=<ip>
# when refreshing the reference routing table in devices.yaml.
DEFAULT_ROUTE_PROBES = [
    "10.52.10.1",
    "10.53.10.1",
    "10.54.10.1",
    "10.55.10.1",
    "10.51.10.1",
    "10.56.10.1",
    "10.57.10.1",
    "10.1.10.1",
    "10.58.10.1",
    "10.99.5.10",
    "172.16.8.20",
]


def parse_lookup_entry(entry: dict, destination: str) -> Route | None:
    """Convert one router/lookup result row into a Route."""
    if not entry:
        return None

    iface = entry.get("interface") or entry.get("ifname") or entry.get("dev")
    if not iface:
        return None

    dst = entry.get("network") or entry.get("ip_mask") or entry.get("ip-mask")
    if dst and "/" not in str(dst):
        try:
            ipaddress.ip_address(str(dst))
            dst = f"{dst}/32"
        except ValueError:
            dst = None
    if not dst:
        dst = f"{destination}/32"

    rtype = str(entry.get("type") or entry.get("route_type") or "static").lower()
    if rtype in {"0", "connected"}:
        rtype = "connected"
    elif rtype in {"1", "static"}:
        rtype = "static"
    elif rtype in {"2", "default"}:
        rtype = "default"

    gateway = entry.get("gateway") or entry.get("gw") or entry.get("gateway-ip")
    gw = None if gateway in (None, "", "0.0.0.0", "0.0.0.0/0") else str(gateway)

    try:
        return Route(dst=str(dst), interface=str(iface), type=rtype, gateway=gw)
    except ValueError:
        return None


def lookup_route(client: FortiGateClient, destination: str) -> Route | None:
    """Query monitor/router/lookup for one destination IP."""
    for entry in client.router_lookup(destination):
        route = parse_lookup_entry(entry, destination)
        if route:
            return route
    return None


def merge_routes(routes: list[Route]) -> list[Route]:
    """Deduplicate routes; keep the most specific prefix per (dst, interface)."""
    best: dict[tuple[str, str], Route] = {}
    for r in routes:
        key = (r.dst, r.interface)
        if key not in best or r.prefixlen > best[key].prefixlen:
            best[key] = r
    return sorted(best.values(), key=lambda x: (x.prefixlen, x.dst), reverse=True)


def route_to_dict(route: Route) -> dict:
    data = {"dst": route.dst, "interface": route.interface, "type": route.type}
    if route.gateway:
        data["gateway"] = route.gateway
    return data


def collect_probe_ips(raw: dict | None = None, extra: list[str] | None = None) -> list[str]:
    """Probe list: route_probes in yaml, then address book subnets, then defaults."""
    raw = raw or {}
    probes: list[str] = list(raw.get("route_probes") or DEFAULT_ROUTE_PROBES)
    for addr in raw.get("addresses") or []:
        subnet = addr.get("subnet")
        if not subnet:
            continue
        try:
            net = ipaddress.ip_network(subnet, strict=False)
            probes.append(str(net.network_address))
        except ValueError:
            continue
    if extra:
        probes.extend(extra)
    # stable unique order
    seen: set[str] = set()
    unique: list[str] = []
    for ip in probes:
        if ip not in seen:
            seen.add(ip)
            unique.append(ip)
    return unique


def sync_device_routes(client: FortiGateClient, probe_ips: list[str]) -> list[Route]:
    """Build a reference route table by calling router/lookup for each probe IP."""
    collected: list[Route] = []
    for ip in probe_ips:
        try:
            route = lookup_route(client, ip)
        except FortiGateError:
            continue
        if route:
            collected.append(route)
    return merge_routes(collected)


def attach_live_clients(devices: list[Device]) -> list[Device]:
    """Return devices wired for live router/lookup (falls back to yaml routes offline)."""
    wired: list[Device] = []
    for dev in devices:
        try:
            cfg = FortiGateConfig.from_device(dev)
            client = FortiGateClient(cfg) if not cfg.dry_run else None
        except RuntimeError:
            client = None
        wired.append(
            Device(
                name=dev.name,
                host=dev.host,
                vdom=dev.vdom,
                token_env=dev.token_env,
                routes=dev.routes,
                client=client,
            )
        )
    return wired


def load_devices_live(path: Path | None = None) -> list[Device]:
    """Load inventory and attach FortiGate clients when not in dry-run mode."""
    return attach_live_clients(load_devices(path))


def _read_devices_doc(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def sync_routes_file(
    path: Path | None = None,
    *,
    write: bool = True,
    probe_ips: list[str] | None = None,
) -> dict[str, list[Route]]:
    """Refresh each device's ``routes`` block from live router/lookup probes."""
    path = path or DEVICES_FILE
    doc = _read_devices_doc(path)
    probes = probe_ips or collect_probe_ips(doc)
    devices = devices_from_dict(doc)
    synced_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    per_device: dict[str, list[Route]] = {}
    for dev in devices:
        cfg = FortiGateConfig.from_device(dev)
        if cfg.dry_run:
            per_device[dev.name] = list(dev.routes)
            continue
        client = FortiGateClient(cfg)
        per_device[dev.name] = sync_device_routes(client, probes)

    if write:
        by_name = {d["name"]: d for d in doc.get("devices", [])}
        for name, routes in per_device.items():
            entry = by_name.get(name)
            if entry is None:
                continue
            entry["routes"] = [route_to_dict(r) for r in routes]
            entry["routes_synced_at"] = synced_at
        path.write_text(
            yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

    return per_device


def load_route_probes_from_repo(addresses_path: Path | None = None) -> list[str]:
    """Merge devices.yaml route_probes with policies/addresses.yaml subnets."""
    doc = _read_devices_doc(DEVICES_FILE)
    addr_doc: dict = {}
    addr_path = addresses_path or (REPO_ROOT / "policies" / "addresses.yaml")
    if addr_path.exists():
        addr_doc = yaml.safe_load(addr_path.read_text(encoding="utf-8")) or {}
    merged = dict(doc)
    merged["addresses"] = addr_doc.get("addresses") or []
    return collect_probe_ips(merged)
