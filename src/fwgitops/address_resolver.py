"""Resolve request inputs (object names or IP/CIDR) to address object names.

A Slack request may name an existing address object directly, or give a raw
IP / CIDR such as ``10.99.5.10`` or ``10.99.5.10/32``.

Matching is intentionally *exact* (object name, or a subnet equal to the
requested network) — we never silently widen a firewall rule to a broader,
already-existing object. When ``autocreate`` is enabled, new objects must
include zone metadata, e.g.::

    myhost=10.51.10.1 prefix=32 zone=ch expire=90 comment=NETOPS-1001
"""

from __future__ import annotations

import ipaddress
import re
from datetime import date

from .expiry import expires_at_from_valid_days, load_expiry_config

_NAMED_ADDR = re.compile(r"^([^=:/\s]{1,50})[:=](\S+)(?:\s+(.*))?$")
_KV_PARAMS = re.compile(r"(\w+)=(\S+)")
_FQDN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,}$")
_DEFAULT_CENTER = "dc1"


def as_network(token: str) -> ipaddress._BaseNetwork | None:
    """Return the network for an IP/CIDR token, or None if it isn't one."""
    try:
        return ipaddress.ip_network(token, strict=False)
    except ValueError:
        return None


def _obj_net(a: dict) -> ipaddress._BaseNetwork | None:
    if a.get("type", "ipmask") == "ipmask" and a.get("subnet"):
        return as_network(a["subnet"])
    return None


def match_exact(token: str, addr_objs: list[dict]) -> str | None:
    """Return an object name if token is an existing name or an exact subnet."""
    if any(a.get("name") == token for a in addr_objs):
        return token

    req = as_network(token)
    if req is None:
        return None
    for a in addr_objs:
        net = _obj_net(a)
        if net is not None and net == req:
            return a["name"]
    return None


def _parse_prefix(raw: str | int | None, default: int = 32) -> tuple[int | None, str | None]:
    if raw is None or str(raw).strip() == "":
        return default, None
    text = str(raw).strip().lstrip("/")
    try:
        plen = int(text)
    except ValueError:
        return None, f"invalid prefix: {raw!r}"
    if plen < 0 or plen > 32:
        return None, f"prefix must be 0–32, got {plen}"
    return plen, None


def _parse_expire_days(
    raw: str | None, rules: dict | None
) -> tuple[date | None, list[str]]:
    if raw is None or str(raw).strip() == "":
        return None, []
    cfg = load_expiry_config(rules or {})
    try:
        days = int(str(raw).strip().split()[0])
    except ValueError:
        return None, ["Expire Day must be a number of days (e.g. 90)."]
    if days <= 0:
        return None, ["Expire Day must be at least 1 day."]
    if days > cfg.max_valid_days:
        return None, [f"Expire Day {days} exceeds max_valid_days={cfg.max_valid_days}."]
    return expires_at_from_valid_days(days), []


def _allowed_zones(rules: dict | None) -> set[str]:
    naming = (rules or {}).get("policy_naming") or {}
    zone_map = naming.get("zone_map") or {}
    return {str(k).lower() for k in zone_map}


def build_address_object(
    *,
    name: str,
    address: str,
    prefix: str | int | None = None,
    zone: str,
    center: str = _DEFAULT_CENTER,
    expires_at: date | None = None,
    comment: str = "",
    taken: set[str],
    rules: dict | None = None,
) -> tuple[dict | None, list[str]]:
    """Build a GitOps address object dict (FortiGate ipmask)."""
    errors: list[str] = []
    obj_name = name.strip()
    zone_key = zone.strip().lower()
    center_key = (center or _DEFAULT_CENTER).strip().lower()

    if not obj_name:
        errors.append("name is required")
    if not zone_key:
        errors.append("zone is required")
    if obj_name in taken:
        errors.append(f"address name `{obj_name}` already exists")

    allowed = _allowed_zones(rules)
    if allowed and zone_key not in allowed:
        errors.append(
            f"zone `{zone_key}` is not in policy_rules policy_naming.zone_map "
            f"({', '.join(sorted(allowed))})"
        )

    net = as_network(address.strip())
    if net is not None:
        ip_str = str(net.network_address)
        plen = net.prefixlen if prefix is None else None
    else:
        try:
            ip_str = str(ipaddress.ip_address(address.strip()))
            plen = None
        except ValueError:
            errors.append(f"invalid address IP: {address!r}")
            return None, errors

    parsed_prefix, perr = _parse_prefix(prefix if plen is None else plen)
    if perr:
        errors.append(perr)
        return None, errors
    assert parsed_prefix is not None

    try:
        subnet = str(ipaddress.ip_network(f"{ip_str}/{parsed_prefix}", strict=False))
    except ValueError as exc:
        errors.append(str(exc))
        return None, errors

    if errors:
        return None, errors

    obj: dict = {
        "name": obj_name,
        "type": "ipmask",
        "subnet": subnet,
        "center": center_key,
        "zone": zone_key,
        "comment": comment.strip() or "Created from Slack request",
    }
    if expires_at is not None:
        obj["expires_at"] = expires_at.isoformat()
    return obj, []


def parse_address_spec(
    token: str,
    taken: set[str],
    comment: str = "",
    *,
    rules: dict | None = None,
    default_center: str = _DEFAULT_CENTER,
) -> tuple[dict | None, list[str]]:
    """Parse ``name=IP prefix=32 zone=ch expire=90 comment=foo``."""
    m = _NAMED_ADDR.match(token.strip())
    if not m:
        return None, []

    obj_name, value, rest = m.group(1), m.group(2), m.group(3) or ""
    params = {k.lower(): v for k, v in _KV_PARAMS.findall(rest)}

    zone = params.get("zone", "")
    if not zone:
        return None, [
            f"`{token}`: new address objects require `zone=` "
            f"(e.g. `{obj_name}={value} prefix=32 zone=ch expire=90`)"
        ]

    center = params.get("center", default_center)
    obj_comment = params.get("comment", comment)

    net = as_network(value)
    if net is not None:
        address = str(net.network_address)
        prefix: str | int | None = net.prefixlen
        if "prefix" in params:
            prefix = params["prefix"]
    elif _looks_like_fqdn(value):
        return _build_fqdn_from_spec(
            obj_name, value, zone, center, params, taken, obj_comment, rules
        )
    else:
        address = value
        prefix = params.get("prefix", "32")

    expire_raw = params.get("expire") or params.get("expires") or params.get("expireday")
    expires_at, exp_errors = _parse_expire_days(expire_raw, rules)
    if exp_errors:
        return None, exp_errors

    return build_address_object(
        name=obj_name,
        address=address,
        prefix=prefix,
        zone=zone,
        center=center,
        expires_at=expires_at,
        comment=obj_comment,
        taken=taken,
        rules=rules,
    )


def _build_fqdn_from_spec(
    obj_name: str,
    fqdn: str,
    zone: str,
    center: str,
    params: dict[str, str],
    taken: set[str],
    comment: str,
    rules: dict | None,
) -> tuple[dict | None, list[str]]:
    errors: list[str] = []
    zone_key = zone.strip().lower()
    if obj_name in taken:
        errors.append(f"address name `{obj_name}` already exists")
    allowed = _allowed_zones(rules)
    if allowed and zone_key not in allowed:
        errors.append(f"zone `{zone_key}` is not in policy_rules policy_naming.zone_map")

    expire_raw = params.get("expire") or params.get("expires") or params.get("expireday")
    expires_at, exp_errors = _parse_expire_days(expire_raw, rules)
    if exp_errors:
        return None, exp_errors
    if errors:
        return None, errors

    obj: dict = {
        "name": obj_name,
        "type": "fqdn",
        "fqdn": fqdn,
        "center": center.strip().lower(),
        "zone": zone_key,
        "comment": comment.strip() or "Created from Slack request",
    }
    if expires_at is not None:
        obj["expires_at"] = expires_at.isoformat()
    return obj, []


def _auto_name(net: ipaddress._BaseNetwork, taken: set[str]) -> str:
    if net.prefixlen == net.max_prefixlen:
        base = f"auto-{net.network_address}"
    else:
        base = f"auto-{net.network_address}_{net.prefixlen}"
    name = base
    i = 2
    while name in taken:
        name = f"{base}-{i}"
        i += 1
    return name


def _looks_like_fqdn(token: str) -> bool:
    return bool(_FQDN.match(token))


def propose_object(
    token: str, taken: set[str], comment: str = "", *, name: str | None = None
) -> dict | None:
    """Build a new ipmask address object for an IP/CIDR token (or None)."""
    net = as_network(token)
    if net is None:
        return None
    obj_name = name or _auto_name(net, taken)
    if obj_name in taken:
        return None
    return {
        "name": obj_name,
        "type": "ipmask",
        "subnet": str(net),
        "comment": comment or "Auto-created from Slack request",
    }


def propose_fqdn_object(
    fqdn: str, taken: set[str], comment: str = "", *, name: str | None = None
) -> dict | None:
    if not _looks_like_fqdn(fqdn):
        return None
    obj_name = name or _auto_fqdn_name(fqdn, taken)
    if obj_name in taken:
        return None
    return {
        "name": obj_name,
        "type": "fqdn",
        "fqdn": fqdn,
        "comment": comment or "Auto-created from Slack request",
    }


def _auto_fqdn_name(fqdn: str, taken: set[str]) -> str:
    slug = fqdn.lower().replace(".", "-")
    base = f"auto-fqdn-{slug}"[:35]
    name = base
    i = 2
    while name in taken:
        name = f"{base}-{i}"[:40]
        i += 1
    return name


def resolve_addresses(
    tokens: list[str],
    addr_objs: list[dict],
    comment: str = "",
    autocreate: bool = False,
    *,
    rules: dict | None = None,
    default_center: str = _DEFAULT_CENTER,
) -> tuple[list[str], list[dict], list[str]]:
    """Resolve tokens to object names.

    Returns ``(names, new_objects, unresolved)`` where ``new_objects`` are
    freshly proposed address objects (only when ``autocreate`` is True) and
    ``unresolved`` are tokens that are neither a known name nor a valid spec.
    """
    names: list[str] = []
    new_objects: list[dict] = []
    unresolved: list[str] = []

    pool = list(addr_objs)
    taken = {a.get("name") for a in addr_objs if a.get("name")}

    for t in tokens:
        name = match_exact(t, pool)
        if name is not None:
            if name not in names:
                names.append(name)
            continue

        if autocreate:
            obj, spec_errors = parse_address_spec(
                t,
                taken,
                comment,
                rules=rules,
                default_center=default_center,
            )
            if obj is not None:
                pool.append(obj)
                taken.add(obj["name"])
                new_objects.append(obj)
                names.append(obj["name"])
                continue
            if spec_errors:
                unresolved.append(f"{t} ({'; '.join(spec_errors)})")
                continue

            # Bare IP/CIDR or FQDN without zone metadata — do not auto-create.
            if as_network(t) is not None or _looks_like_fqdn(t):
                unresolved.append(
                    f"{t} (new objects need zone= — use "
                    f"`name={t} prefix=32 zone=ch expire=90` or `/fw-address`)"
                )
                continue

        unresolved.append(t)

    return names, new_objects, unresolved
