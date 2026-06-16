"""Route-aware target firewall selection.

Given a desired policy (its source/destination address objects) this module
decides which firewall(s) from ``config/devices.yaml`` are on the traffic path
and should therefore enforce the policy.

Selection criterion (transit): a firewall is a candidate when the source
resolves to one interface and the destination to a *different* interface, i.e.
the traffic genuinely passes *through* the device. When several firewalls are on
the path, the one whose matched routes are the most specific (longest prefix
match) is recommended.

In dry-run mode the routing tables come from ``devices.yaml`` ('routes'). With a
live device the same logic runs against
``GET /api/v2/monitor/router/lookup?destination=<ip>``.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from .config import REPO_ROOT
from .models import Address, Policy

if TYPE_CHECKING:
    from .fortigate import FortiGateClient

DEVICES_FILE = REPO_ROOT / "config" / "devices.yaml"


# --------------------------------------------------------------------------- #
# Inventory model
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Route:
    dst: str  # CIDR, e.g. "10.20.0.0/16" or "0.0.0.0/0"
    interface: str
    type: str = "static"  # connected | static | default
    gateway: str | None = None

    @property
    def network(self) -> ipaddress.IPv4Network:
        return ipaddress.ip_network(self.dst, strict=False)

    @property
    def prefixlen(self) -> int:
        return self.network.prefixlen

    @property
    def is_default(self) -> bool:
        return self.prefixlen == 0 or self.type == "default"


@dataclass
class Device:
    name: str
    host: str = ""
    vdom: str | None = None
    token_env: str | None = None
    routes: list[Route] = field(default_factory=list)
    client: FortiGateClient | None = field(default=None, repr=False, compare=False)

    def lookup(self, ip: str) -> Route | None:
        """Longest-prefix-match route lookup for a single IP address.

        When ``client`` is set (live FortiGate), uses
        ``GET /api/v2/monitor/router/lookup?destination=<ip>`` first, then
        falls back to the static ``routes`` table from devices.yaml.
        """
        if self.client is not None:
            from .router_monitor import lookup_route

            try:
                live = lookup_route(self.client, ip)
            except Exception:
                live = None
            if live is not None:
                return live

        addr = ipaddress.ip_address(ip)
        best: Route | None = None
        for r in self.routes:
            if addr in r.network and (best is None or r.prefixlen > best.prefixlen):
                best = r
        return best


def devices_from_dict(raw: dict | None) -> list[Device]:
    """Build Device objects from an already-parsed devices.yaml mapping."""
    devices: list[Device] = []
    for d in (raw or {}).get("devices", []):
        routes = [Route(**r) for r in d.get("routes", [])]
        devices.append(
            Device(
                name=d["name"],
                host=d.get("host", ""),
                vdom=d.get("vdom"),
                token_env=d.get("token_env"),
                routes=routes,
            )
        )
    return devices


def load_devices(path: Path | None = None) -> list[Device]:
    p = path or DEVICES_FILE
    if not p.exists():
        return []
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return devices_from_dict(raw)


# --------------------------------------------------------------------------- #
# Address resolution
# --------------------------------------------------------------------------- #
def _addr_to_ip(addr: Address) -> str | None:
    """Pick a representative IP from an address object for route lookup."""
    if addr.type == "ipmask" and addr.subnet:
        net = ipaddress.ip_network(addr.subnet, strict=False)
        return str(net.network_address)
    if addr.type == "iprange" and addr.start_ip:
        return addr.start_ip
    return None  # fqdn cannot be resolved offline


def resolve_ips(names: list[str], addr_index: dict[str, Address]) -> list[str]:
    ips: list[str] = []
    for name in names:
        addr = addr_index.get(name)
        if addr is None:
            continue
        ip = _addr_to_ip(addr)
        if ip:
            ips.append(ip)
    return ips


# --------------------------------------------------------------------------- #
# Selection
# --------------------------------------------------------------------------- #
@dataclass
class DeviceMatch:
    device: str
    src_route: Route | None
    dst_route: Route | None

    @property
    def is_transit(self) -> bool:
        return (
            self.src_route is not None
            and self.dst_route is not None
            and self.src_route.interface != self.dst_route.interface
        )

    @property
    def specificity(self) -> int:
        """Higher = more specific match (longer combined prefixes)."""
        s = self.src_route.prefixlen if self.src_route else 0
        d = self.dst_route.prefixlen if self.dst_route else 0
        return s + d

    @property
    def reason(self) -> str:
        if self.src_route is None and self.dst_route is None:
            return "no route to src or dst"
        if self.src_route is None:
            return "no route to src"
        if self.dst_route is None:
            return "no route to dst"
        if not self.is_transit:
            return (
                f"src and dst share interface '{self.src_route.interface}' "
                "(not transit)"
            )
        return (
            f"transit {self.src_route.interface} -> {self.dst_route.interface}"
        )


@dataclass
class Selection:
    matches: list[DeviceMatch]

    @property
    def transit(self) -> list[DeviceMatch]:
        return sorted(
            (m for m in self.matches if m.is_transit),
            key=lambda m: m.specificity,
            reverse=True,
        )

    @property
    def chosen(self) -> DeviceMatch | None:
        ranked = self.transit
        return ranked[0] if ranked else None


def select_targets(
    policy: Policy,
    addr_index: dict[str, Address],
    devices: list[Device],
) -> Selection:
    """Return per-device matches and the recommended transit firewall."""
    src_ips = resolve_ips(policy.srcaddr, addr_index)
    dst_ips = resolve_ips(policy.dstaddr, addr_index)

    matches: list[DeviceMatch] = []
    for dev in devices:
        src_route = _best_route(dev, src_ips)
        dst_route = _best_route(dev, dst_ips)
        matches.append(DeviceMatch(dev.name, src_route, dst_route))
    return Selection(matches)


def _best_route(dev: Device, ips: list[str]) -> Route | None:
    """Most specific route across the given IPs for one device."""
    best: Route | None = None
    for ip in ips:
        r = dev.lookup(ip)
        if r is not None and (best is None or r.prefixlen > best.prefixlen):
            best = r
    return best
