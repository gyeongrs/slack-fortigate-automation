"""Apply a computed plan to the FortiGate. Order matters: addresses and
services must exist before policies that reference them."""

from __future__ import annotations

from .fortigate import FortiGateClient, FortiGateError
from .planner import Plan, PlanItem

_KIND_ORDER = {"address": 0, "service": 1, "policy": 2}


def apply_plan(plan: Plan, client: FortiGateClient) -> list[str]:
    """Execute create/update actions. Returns a log of applied changes."""
    log: list[str] = []
    for item in sorted(plan.changed, key=lambda i: _KIND_ORDER[i.kind]):
        log.append(_apply_item(item, client))
    return log


def _apply_item(item: PlanItem, client: FortiGateClient) -> str:
    try:
        if item.action == "create":
            client.create_object(item.endpoint, item.body)
            return f"[created] {item.kind} '{item.name}'"
        if item.action == "update":
            client.update_object(item.endpoint, item.mkey or item.name, item.body)
            detail = "; ".join(item.changes) if item.changes else "fields updated"
            return f"[updated] {item.kind} '{item.name}' ({detail})"
    except FortiGateError as exc:
        return f"[ERROR] {item.kind} '{item.name}': {exc}"
    return f"[skip] {item.kind} '{item.name}'"
