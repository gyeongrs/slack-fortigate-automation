"""Resolve request service tokens to catalog names.

Accepts built-in FortiGate services (HTTPS, …), names from ``services.yaml``,
or port specifications such as ``8443``, ``tcp/8443``, ``TCP-9000`` which
propose a new custom service in the same pull request.
"""

from __future__ import annotations

import re

_PORT_SPEC = re.compile(
    r"^(?:(?P<proto1>tcp|udp)[/: ]+)?(?P<port>\d+(?:-\d+)?)"
    r"(?:[/:](?P<proto2>tcp|udp))?$",
    re.IGNORECASE,
)
_NAMED_SERVICE = re.compile(r"^([^=:/\s]{1,50})[:=](.+)$", re.IGNORECASE)
_TCP_NAME = re.compile(r"^TCP[-_]?(\d+(?:-\d+)?)$", re.IGNORECASE)
_UDP_NAME = re.compile(r"^UDP[-_]?(\d+(?:-\d+)?)$", re.IGNORECASE)


def _service_names(service_objs: list[dict]) -> set[str]:
    return {s["name"] for s in service_objs if s.get("name")}


def _find_service(token: str, service_objs: list[dict]) -> str | None:
    if any(s.get("name") == token for s in service_objs):
        return token
    return None


def _normalize_builtin(token: str, builtin_services: set[str]) -> str | None:
    by_upper = {b.upper(): b for b in builtin_services}
    return by_upper.get(token.upper())


def _parse_port_spec(token: str) -> tuple[str, str] | None:
    """Return (protocol, portrange) for tcp/8443-style tokens."""
    m = _PORT_SPEC.match(token.strip())
    if not m:
        return None
    proto = (m.group("proto1") or m.group("proto2") or "tcp").upper()
    port = m.group("port")
    return proto, port


def _auto_service_name(proto: str, port: str, taken: set[str]) -> str:
    base = f"auto-{proto.lower()}-{port.replace('-', '_')}"
    name = base
    i = 2
    while name in taken:
        name = f"{base}-{i}"
        i += 1
    return name


def propose_service(
    *,
    name: str,
    protocol: str,
    portrange: str,
    comment: str = "",
) -> dict:
    body: dict = {
        "name": name,
        "protocol": protocol,
        "comment": comment or "Auto-created from Slack request",
    }
    if protocol == "UDP":
        body["udp_portrange"] = portrange
    else:
        body["tcp_portrange"] = portrange
    return body


def _propose_from_port_spec(
    token: str,
    taken: set[str],
    comment: str,
    preferred_name: str | None = None,
) -> dict | None:
    parsed = _parse_port_spec(token)
    if parsed is None:
        m = _TCP_NAME.match(token)
        if m:
            parsed = ("TCP", m.group(1))
        else:
            m = _UDP_NAME.match(token)
            if m:
                parsed = ("UDP", m.group(1))
    if parsed is None:
        return None

    proto, port = parsed
    name = preferred_name or _auto_service_name(proto, port, taken)
    if name in taken:
        return None
    return propose_service(name=name, protocol=proto, portrange=port, comment=comment)


def resolve_services(
    tokens: list[str],
    service_objs: list[dict],
    builtin_services: set[str],
    comment: str = "",
    autocreate: bool = False,
) -> tuple[list[str], list[dict], list[str]]:
    """Resolve tokens to service names.

    Returns ``(names, new_services, unresolved)``.
    """
    names: list[str] = []
    new_services: list[dict] = []
    unresolved: list[str] = []

    pool = list(service_objs)
    taken = _service_names(pool) | set(builtin_services)

    for token in tokens:
        existing = _find_service(token, pool)
        if existing is not None:
            if existing not in names:
                names.append(existing)
            continue

        builtin = _normalize_builtin(token, builtin_services)
        if builtin is not None:
            if builtin not in names:
                names.append(builtin)
            continue

        if autocreate:
            named = _NAMED_SERVICE.match(token)
            if named:
                svc_name, spec = named.group(1), named.group(2)
                if svc_name in taken:
                    if svc_name not in names:
                        names.append(svc_name)
                    continue
                obj = _propose_from_port_spec(
                    spec, taken, comment, preferred_name=svc_name
                )
                if obj is not None:
                    pool.append(obj)
                    taken.add(obj["name"])
                    new_services.append(obj)
                    names.append(obj["name"])
                    continue

            obj = _propose_from_port_spec(token, taken, comment)
            if obj is not None:
                pool.append(obj)
                taken.add(obj["name"])
                new_services.append(obj)
                names.append(obj["name"])
                continue

        unresolved.append(token)

    return names, new_services, unresolved
