"""Multi-device apply: shared catalog + per-device policies.

``policies/services.yaml`` is a **global catalog** — every firewall in
``config/devices.yaml`` receives the same custom service objects. Addresses are
also pushed to every device so policies can reference them. Firewall policies
with a ``device`` field are applied only on that target; policies without
``device`` are applied on every device (legacy / global rules).
"""

from __future__ import annotations

import os

from .applier import apply_plan
from .config import FortiGateConfig
from .fortigate import FortiGateClient
from .models import DesiredState
from .planner import Plan, build_plan
from .route_selector import Device, load_devices


def state_for_device(state: DesiredState, device_name: str) -> DesiredState:
    """Shared addresses/services; policies scoped to this device."""
    policies = [
        p
        for p in state.policies
        if p.device is None or p.device == device_name
    ]
    return DesiredState(
        addresses=list(state.addresses),
        services=list(state.services),
        policies=policies,
    )


def build_device_plan(state: DesiredState, device: Device) -> Plan:
    cfg = FortiGateConfig.from_device(device)
    client = FortiGateClient(cfg)
    scoped = state_for_device(state, device.name)
    return build_plan(scoped, client)


def apply_all_devices(state: DesiredState) -> list[str]:
    """Apply shared services (and addresses/policies) to every inventory device."""
    devices = load_devices()
    if not devices:
        cfg = FortiGateConfig.from_env()
        plan = build_plan(state, FortiGateClient(cfg))
        return [f"[device default] {line}" for line in apply_plan(plan, FortiGateClient(cfg))]

    log: list[str] = []
    for dev in devices:
        cfg = FortiGateConfig.from_device(dev)
        client = FortiGateClient(cfg)
        scoped = state_for_device(state, dev.name)
        plan = build_plan(scoped, client)
        if not plan.changed:
            log.append(f"[{dev.name}] nothing to apply")
            continue
        log.append(
            f"[{dev.name}] applying {len(plan.changed)} change(s) "
            f"(shared services: {len(state.services)}, policies: {len(scoped.policies)})"
        )
        for line in apply_plan(plan, client):
            log.append(f"[{dev.name}] {line}")
    return log


def combined_plan(state: DesiredState) -> tuple[list[Plan], list[Device]]:
    """One plan per inventory device (for display / tripwire counting)."""
    devices = load_devices()
    if not devices:
        cfg = FortiGateConfig.from_env()
        return [build_plan(state, FortiGateClient(cfg))], []
    return [build_device_plan(state, d) for d in devices], devices
