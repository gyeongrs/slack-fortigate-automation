"""Safety guardrails. Runs before any plan/apply and in CI on every PR."""

from __future__ import annotations

import re
from datetime import date

from .expiry import load_expiry_config
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
    expiry_cfg = load_expiry_config(rules)
    today = date.today()

    # Map of service name -> ports, from custom services in desired state.
    custom_service_ports: dict[str, set[int]] = {}
    for svc in state.services:
        custom_service_ports[svc.name] = _ports_from_range(
            svc.tcp_portrange
        ) | _ports_from_range(svc.udp_portrange)

    for pol in state.policies:
        errors.extend(
            _validate_policy(pol, forbid_any, allowed_ifaces, require, expiry_cfg, today)
        )
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
    object to silently overwrite another. Policy names are scoped per device."""
    errs: list[str] = []
    for kind, items in (
        ("address", state.addresses),
        ("service", state.services),
        ("policy", state.policies),
    ):
        seen: set[str | tuple[str, str]] = set()
        for obj in items:
            if kind == "policy":
                key: str | tuple[str, str] = (obj.device or "", obj.name)
            else:
                key = obj.name
            if key in seen:
                if kind == "policy":
                    _dev, pname = key  # type: ignore[misc]
                    loc = f" on device '{_dev}'" if _dev else ""
                    errs.append(f"duplicate policy name '{pname}'{loc}.")
                else:
                    errs.append(f"duplicate {kind} name '{obj.name}'.")
            seen.add(key)
    return errs


def _validate_policy(
    pol: Policy,
    forbid_any: dict,
    allowed_ifaces: set,
    require: dict,
    expiry_cfg,
    today: date,
) -> list[str]:
    errs: list[str] = []
    prefix = f"policy '{pol.name}'"

    if pol.expires_at is not None:
        if pol.expires_at < today:
            errs.append(
                f"{prefix}: expires_at {pol.expires_at} is in the past "
                f"(remove or extend the policy)."
            )
        span = (pol.expires_at - today).days
        if span > expiry_cfg.max_valid_days:
            errs.append(
                f"{prefix}: validity span {span} days exceeds "
                f"max_valid_days={expiry_cfg.max_valid_days}."
            )
        if pol.alert_days_before is not None and pol.alert_days_before < 0:
            errs.append(f"{prefix}: alert_days_before must be >= 0.")

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
        if field == "schedule" and pol.expires_at is not None:
            continue  # temporary policies use auto-generated one-time schedules
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
