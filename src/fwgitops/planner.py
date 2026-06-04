"""Compute a plan (create/update/no-op) by diffing desired vs. current state.

Deletes are deliberately NOT performed automatically: objects present on the
device but missing from YAML are left untouched. Removal is a manual,
explicit operation to avoid accidental outages.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import MANAGED_TAG
from .fortigate import FortiGateClient
from .models import Address, DesiredState, Policy, Service

Action = str  # "create" | "update" | "noop"


@dataclass
class PlanItem:
    kind: str          # "address" | "service" | "policy"
    name: str
    action: Action
    endpoint: str
    body: dict
    mkey: str | None = None
    changes: list[str] = field(default_factory=list)


@dataclass
class Plan:
    items: list[PlanItem] = field(default_factory=list)

    @property
    def changed(self) -> list[PlanItem]:
        return [i for i in self.items if i.action != "noop"]

    def summary(self) -> str:
        c = sum(1 for i in self.items if i.action == "create")
        u = sum(1 for i in self.items if i.action == "update")
        n = sum(1 for i in self.items if i.action == "noop")
        return f"{c} to create, {u} to update, {n} unchanged"


# -- body builders -------------------------------------------------------
def _with_tag(comment: str) -> str:
    comment = comment.strip()
    if MANAGED_TAG in comment:
        return comment
    return f"{comment} [{MANAGED_TAG}]".strip()


def address_body(a: Address) -> dict:
    body: dict = {"name": a.name, "type": a.type, "comment": _with_tag(a.comment)}
    if a.type == "ipmask" and a.subnet:
        body["subnet"] = a.subnet
    elif a.type == "iprange":
        body["start-ip"] = a.start_ip
        body["end-ip"] = a.end_ip
    elif a.type == "fqdn":
        body["fqdn"] = a.fqdn
    return body


def service_body(s: Service) -> dict:
    body: dict = {
        "name": s.name,
        "protocol": s.protocol,
        "comment": _with_tag(s.comment),
    }
    if s.tcp_portrange:
        body["tcp-portrange"] = s.tcp_portrange
    if s.udp_portrange:
        body["udp-portrange"] = s.udp_portrange
    return body


def policy_body(p: Policy) -> dict:
    return {
        "name": p.name,
        "srcintf": [{"name": i} for i in p.srcintf],
        "dstintf": [{"name": i} for i in p.dstintf],
        "srcaddr": [{"name": a} for a in p.srcaddr],
        "dstaddr": [{"name": a} for a in p.dstaddr],
        "service": [{"name": s} for s in p.service],
        "action": p.action,
        "schedule": p.schedule,
        "logtraffic": p.logtraffic,
        "status": p.status,
        "nat": "enable" if p.nat else "disable",
        "comments": _with_tag(p.comment),
    }


# -- diff helpers --------------------------------------------------------
def _names(value) -> set[str]:
    """Normalize a FortiGate list-of-dicts or our list-of-dicts to a name set."""
    if isinstance(value, list):
        return {v.get("name", "") for v in value if isinstance(v, dict)}
    return set()


def _diff(desired: dict, current: dict) -> list[str]:
    changes: list[str] = []
    for key, want in desired.items():
        have = current.get(key)
        if isinstance(want, list):
            if _names(want) != _names(have):
                changes.append(f"{key}: {_names(have)} -> {_names(want)}")
        else:
            if str(have) != str(want):
                changes.append(f"{key}: {have!r} -> {want!r}")
    return changes


def _plan_group(
    kind: str,
    endpoint: str,
    desired_items: list,
    current: dict[str, dict],
    body_fn,
) -> list[PlanItem]:
    items: list[PlanItem] = []
    for obj in desired_items:
        body = body_fn(obj)
        existing = current.get(obj.name)
        if existing is None:
            items.append(
                PlanItem(kind, obj.name, "create", endpoint, body)
            )
            continue
        changes = _diff(body, existing)
        action = "update" if changes else "noop"
        items.append(
            PlanItem(
                kind, obj.name, action, endpoint, body,
                mkey=str(existing.get("name", obj.name)), changes=changes,
            )
        )
    return items


def build_plan(state: DesiredState, client: FortiGateClient) -> Plan:
    plan = Plan()
    plan.items += _plan_group(
        "address", "firewall/address", state.addresses,
        client.get_addresses(), address_body,
    )
    plan.items += _plan_group(
        "service", "firewall.service/custom", state.services,
        client.get_services(), service_body,
    )
    plan.items += _plan_group(
        "policy", "firewall/policy", state.policies,
        client.get_policies(), policy_body,
    )
    return plan
