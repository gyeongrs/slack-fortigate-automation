"""Resolve request inputs (object names or IP/CIDR) to address object names.

A Slack request may name an existing address object directly, or give a raw
IP / CIDR such as ``10.99.5.10`` or ``10.99.5.10/32``.

Matching is intentionally *exact* (object name, or a subnet equal to the
requested network) — we never silently widen a firewall rule to a broader,
already-existing object. When ``autocreate`` is enabled and an IP/CIDR matches
nothing, a brand-new ``ipmask`` object is proposed so it can be added to the
same pull request.
"""

from __future__ import annotations

import ipaddress


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


def propose_object(
    token: str, taken: set[str], comment: str = ""
) -> dict | None:
    """Build a new ipmask address object for an IP/CIDR token (or None)."""
    net = as_network(token)
    if net is None:
        return None
    return {
        "name": _auto_name(net, taken),
        "type": "ipmask",
        "subnet": str(net),
        "comment": comment or "Auto-created from Slack request",
    }


def resolve_addresses(
    tokens: list[str],
    addr_objs: list[dict],
    comment: str = "",
    autocreate: bool = False,
) -> tuple[list[str], list[dict], list[str]]:
    """Resolve tokens to object names.

    Returns ``(names, new_objects, unresolved)`` where ``new_objects`` are
    freshly proposed address objects (only when ``autocreate`` is True) and
    ``unresolved`` are tokens that are neither a known name nor an IP/CIDR.
    """
    names: list[str] = []
    new_objects: list[dict] = []
    unresolved: list[str] = []

    pool = list(addr_objs)  # existing + anything we propose, for dedup/matching
    taken = {a.get("name") for a in addr_objs if a.get("name")}

    for t in tokens:
        name = match_exact(t, pool)
        if name is not None:
            if name not in names:
                names.append(name)
            continue

        if autocreate:
            obj = propose_object(t, taken, comment)
            if obj is not None:
                pool.append(obj)
                taken.add(obj["name"])
                new_objects.append(obj)
                names.append(obj["name"])
                continue

        unresolved.append(t)

    return names, new_objects, unresolved
