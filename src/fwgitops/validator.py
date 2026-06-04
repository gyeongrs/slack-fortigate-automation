"""Safety guardrails. Runs before any plan/apply and in CI on every PR."""

from __future__ import annotations

import re

from .models import DesiredState, Policy

_ANY_TOKENS = {"all", "any"}


def _ports_from_range(portrange: str | None) -> set[int]:
    ports: set[int] = set()
    if not portrange:
        return ports
    for chunk in re.split(r"[\s,]+", portrange.strip()):
        if not chunk:
            continue
        if "-" in chunk:
            lo, hi = chunk.split("-", 1)
            try:
                ports.update(range(int(lo), int(hi) + 1))
            except ValueError:
                continue
        else:
            try:
                ports.add(int(chunk))
            except ValueError:
                continue
    return ports


def validate(state: DesiredState, rules: dict) -> list[str]:
    """Return a list of human-readable violations. Empty list == valid."""
    errors: list[str] = []
    forbid_any = rules.get("forbid_any", {})
    allowed_ifaces = set(rules.get("allowed_interfaces", []))
    forbidden_ports = set(rules.get("forbidden_ports", []))
    require = rules.get("require", {})

    # Map of service name -> ports, from custom services in desired state.
    custom_service_ports: dict[str, set[int]] = {}
    for svc in state.services:
        custom_service_ports[svc.name] = _ports_from_range(
            svc.tcp_portrange
        ) | _ports_from_range(svc.udp_portrange)

    for pol in state.policies:
        errors.extend(_validate_policy(pol, forbid_any, allowed_ifaces, require))
        _check_forbidden_ports(
            pol, custom_service_ports, forbidden_ports, errors
        )

    errors.extend(_check_references(state, rules))
    errors.extend(_check_duplicates(state))
    return errors


def _check_references(state: DesiredState, rules: dict) -> list[str]:
    """Every address/service a policy references must be resolvable, so the
    apply does not fail on the device with a dangling reference."""
    errs: list[str] = []
    defined_addresses = {a.name for a in state.addresses}
    defined_services = {s.name for s in state.services}
    builtin_services = set(rules.get("allowed_builtin_services", []))

    for pol in state.policies:
        for field in ("srcaddr", "dstaddr"):
            for name in getattr(pol, field):
                if name.strip().lower() in _ANY_TOKENS:
                    continue  # handled by forbid_any
                if name not in defined_addresses:
                    errs.append(
                        f"policy '{pol.name}': {field} '{name}' is not defined "
                        f"in addresses.yaml."
                    )
        for name in pol.service:
            if name.strip().lower() in _ANY_TOKENS:
                continue
            if name not in defined_services and name not in builtin_services:
                errs.append(
                    f"policy '{pol.name}': service '{name}' is neither a custom "
                    f"service (services.yaml) nor an allowed built-in service."
                )
    return errs


def _check_duplicates(state: DesiredState) -> list[str]:
    """Names are the match key for the engine, so duplicates would cause one
    object to silently overwrite another."""
    errs: list[str] = []
    for kind, items in (
        ("address", state.addresses),
        ("service", state.services),
        ("policy", state.policies),
    ):
        seen: set[str] = set()
        for obj in items:
            if obj.name in seen:
                errs.append(f"duplicate {kind} name '{obj.name}'.")
            seen.add(obj.name)
    return errs


def _validate_policy(
    pol: Policy, forbid_any: dict, allowed_ifaces: set, require: dict
) -> list[str]:
    errs: list[str] = []
    prefix = f"policy '{pol.name}'"

    if forbid_any.get("srcaddr") and _has_any(pol.srcaddr):
        errs.append(f"{prefix}: srcaddr must not be 'all'/'any'.")
    if forbid_any.get("dstaddr") and _has_any(pol.dstaddr):
        errs.append(f"{prefix}: dstaddr must not be 'all'/'any'.")
    if forbid_any.get("service") and _has_any(pol.service):
        errs.append(f"{prefix}: service must not be 'ALL'/'any'.")

    for iface in [*pol.srcintf, *pol.dstintf]:
        if allowed_ifaces and iface not in allowed_ifaces:
            errs.append(
                f"{prefix}: interface '{iface}' is not in allowed_interfaces."
            )

    for field, expected in require.items():
        actual = getattr(pol, field, None)
        if actual != expected:
            errs.append(
                f"{prefix}: {field} must be '{expected}' (got '{actual}')."
            )
    return errs


def _check_forbidden_ports(
    pol: Policy,
    custom_service_ports: dict[str, set[int]],
    forbidden_ports: set[int],
    errors: list[str],
) -> None:
    if not forbidden_ports:
        return
    for svc_name in pol.service:
        ports = custom_service_ports.get(svc_name)
        if not ports:
            continue
        bad = sorted(ports & forbidden_ports)
        if bad:
            errors.append(
                f"policy '{pol.name}': service '{svc_name}' opens "
                f"forbidden port(s) {bad}."
            )


def _has_any(values: list[str]) -> bool:
    return any(v.strip().lower() in _ANY_TOKENS for v in values)
