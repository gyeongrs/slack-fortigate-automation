"""Auto-generate FortiGate policy names from address object center/zone + IP.

Each address in ``addresses.yaml`` carries GitOps-only ``center`` and ``zone``.
Policy names describe the traffic flow:

  ``{center}{zone}-{src_ip}>{center}{zone}-{dst_ip}``

Example (NEF-10.54.20.20 dc1/inet → Azure-10.56.10.1 dc1/svr):

  ``dc1inet-10.54.20.20>dc1svr-10.56.10.1``

Uses the raw ``center`` / ``zone`` keys from the address object (not
``center_map`` / ``zone_map`` abbreviations). Same name on every transit FW.
"""

from __future__ import annotations

import ipaddress
import re

from .address_resolver import as_network

_FORTIGATE_NAME_MAX = 35
_DEVICE_SUFFIX = "-fw"
_DEFAULT_CODE_LEN = 2


def load_naming_config(rules: dict) -> dict:
    return rules.get("policy_naming") or {}


def parse_device_segments(device_name: str) -> tuple[str | None, str | None]:
    """Return (center, zone) from ``{center}-{zone}-fw`` or zone-only ``{zone}-fw``."""
    name = device_name
    if name.endswith(_DEVICE_SUFFIX):
        name = name[: -len(_DEVICE_SUFFIX)]
    parts = [p for p in name.split("-") if p]
    if len(parts) >= 2:
        return parts[0], parts[1]
    if len(parts) == 1:
        return None, parts[0]
    return None, None


def _lookup_code(key: str | None, mapping: dict, fallback: str) -> str:
    if not key:
        return fallback
    if key in mapping:
        return str(mapping[key])
    return key[:_DEFAULT_CODE_LEN].upper()


def _center_zone_codes(center: str | None, zone: str | None, naming: dict) -> str:
    center_map = naming.get("center_map") or {}
    zone_map = naming.get("zone_map") or {}
    default_center = str(
        naming.get("default_center_code")
        or naming.get("default_center_letter")
        or "00"
    )

    legacy = naming.get("letter_map") or {}
    if legacy and not center_map and not zone_map:
        center_map = legacy
        zone_map = legacy

    center_code = _lookup_code(center, center_map, default_center)
    zone_code = _lookup_code(zone, zone_map, "ZZ")
    return f"{center_code}{zone_code}"


def device_prefix(device_name: str, naming: dict) -> str:
    """Prefix from firewall inventory name (``dc1-core-fw`` → ``D1CR``)."""
    center, zone = parse_device_segments(device_name)
    return _center_zone_codes(center, zone, naming)


def _find_address(addr_name: str, addr_objs: list[dict]) -> dict | None:
    for obj in addr_objs:
        if obj.get("name") == addr_name:
            return obj
    return None


def address_flow_segment(addr_name: str, addr_objs: list[dict]) -> str:
    """``{center}{zone}-{ip}`` from ``addresses.yaml`` labels + endpoint IP."""
    ip = endpoint_token(addr_name, addr_objs)
    obj = _find_address(addr_name, addr_objs)
    if obj is not None:
        center = str(obj.get("center") or "").strip().lower()
        zone = str(obj.get("zone") or "").strip().lower()
        if center or zone:
            return f"{center}{zone}-{ip}"
    return ip or "?"


def address_prefix(addr_name: str, addr_objs: list[dict], naming: dict) -> str:
    """Legacy alias — prefer ``address_flow_segment`` for policy names."""
    _ = naming
    seg = address_flow_segment(addr_name, addr_objs)
    if "-" in seg:
        return seg.split("-", 1)[0]
    return seg


def endpoint_token(name: str, addr_objs: list[dict]) -> str:
    """Dotted IP (or FQDN slug) — used in Slack summaries, not policy names."""
    for obj in addr_objs:
        if obj.get("name") != name:
            continue
        if obj.get("type", "ipmask") == "ipmask" and obj.get("subnet"):
            net = ipaddress.ip_network(obj["subnet"], strict=False)
            return str(net.network_address)
        if obj.get("type") == "iprange" and obj.get("start_ip"):
            return obj["start_ip"]
        if obj.get("type") == "fqdn" and obj.get("fqdn"):
            return obj["fqdn"]
    net = as_network(name)
    if net is not None:
        return str(net.network_address)
    return re.sub(r"[^\w.-]", "-", name)[:24]


def build_policy_name(
    device: str,
    src_names: list[str],
    dst_names: list[str],
    addr_objs: list[dict],
    naming: dict,
) -> str:
    """Flow name: ``dc1inet-10.54.20.20>dc1svr-10.56.10.1``."""
    _ = device, naming
    src = address_flow_segment(src_names[0], addr_objs) if src_names else "?"
    dst = address_flow_segment(dst_names[0], addr_objs) if dst_names else "?"
    name = f"{src}>{dst}"
    if len(name) > _FORTIGATE_NAME_MAX:
        name = name[:_FORTIGATE_NAME_MAX]
    return name


def request_summary_name(
    src_names: list[str],
    dst_names: list[str],
    addr_objs: list[dict],
    naming: dict | None = None,
) -> str:
    """PR title / Slack summary — same flow label as the policy name."""
    naming = naming or {}
    return build_policy_name("", src_names, dst_names, addr_objs, naming)
