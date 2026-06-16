"""Auto-generate FortiGate policy names from device + endpoint IPs.

Inventory device names use ``{center}-{zone}-fw`` (e.g. ``dc1-core-fw``):
  - ``dc1``  → center code from ``center_map``  (any short string you like)
  - ``core`` → zone code from ``zone_map``
  - prefix   → ``{center_code}{zone_code}``  e.g. ``D1`` + ``CR`` → ``D1CR``

Policy name: ``{prefix}{src_ip}>{prefix}{dst_ip}``
e.g. ``D1CR10.50.1.1>D1CR10.51.10.1`` (FortiGate name max 35 chars — keep codes short).
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
    # Not mapped: use up to 2 chars from the segment name (e.g. ch → CH)
    return key[:_DEFAULT_CODE_LEN].upper()


def device_prefix(device_name: str, naming: dict) -> str:
    """Prefix = center code + zone code (both configurable, not limited to A/B)."""
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

    center, zone = parse_device_segments(device_name)
    center_code = _lookup_code(center, center_map, default_center)
    zone_code = _lookup_code(zone, zone_map, "ZZ")
    return f"{center_code}{zone_code}"


def endpoint_token(name: str, addr_objs: list[dict]) -> str:
    """Dotted IP (or FQDN slug) used inside an auto-generated policy name."""
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
    prefix = device_prefix(device, naming)
    src = endpoint_token(src_names[0], addr_objs) if src_names else "?"
    dst = endpoint_token(dst_names[0], addr_objs) if dst_names else "?"
    name = f"{prefix}{src}>{prefix}{dst}"
    if len(name) > _FORTIGATE_NAME_MAX:
        name = name[:_FORTIGATE_NAME_MAX]
    return name


def request_summary_name(
    src_names: list[str],
    dst_names: list[str],
    addr_objs: list[dict],
) -> str:
    """PR title / Slack summary when several firewalls share one request."""
    src = endpoint_token(src_names[0], addr_objs) if src_names else "?"
    dst = endpoint_token(dst_names[0], addr_objs) if dst_names else "?"
    return f"{src}>{dst}"
