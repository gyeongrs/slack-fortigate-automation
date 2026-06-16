"""Policy expiry helpers: validation, FortiGate schedule names, alert selection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from .models import Policy

SCHEDULE_PREFIX = "fwgitops-"


@dataclass(frozen=True)
class ExpiryConfig:
    default_valid_days: int = 90
    alert_days_before: tuple[int, ...] = (14, 7, 1)
    max_valid_days: int = 365


@dataclass(frozen=True)
class ExpiryAlert:
    policy: Policy
    days_until: int
    kind: str  # "warning" | "expires_today" | "expired"


def load_expiry_config(rules: dict) -> ExpiryConfig:
    raw = rules.get("expiry") or {}
    days = raw.get("alert_days_before", [14, 7, 1])
    if isinstance(days, int):
        days = [days]
    return ExpiryConfig(
        default_valid_days=int(raw.get("default_valid_days", 90)),
        alert_days_before=tuple(int(d) for d in days),
        max_valid_days=int(raw.get("max_valid_days", 365)),
    )


def schedule_name_for_policy(policy: Policy) -> str:
    """FortiGate one-time schedule name tied to a temporary policy."""
    slug = policy.name.lower().replace(" ", "-")
    keep = [c if c.isalnum() or c in "-_" else "-" for c in slug]
    base = SCHEDULE_PREFIX + "".join(keep).strip("-")
    return base[:35] or "fwgitops-temp"


def schedule_body(policy: Policy, *, start: date | None = None) -> dict:
    if policy.expires_at is None:
        raise ValueError(f"policy '{policy.name}' has no expires_at")
    start_date = start or date.today()
    return {
        "name": schedule_name_for_policy(policy),
        "start-date": start_date.isoformat(),
        "end-date": policy.expires_at.isoformat(),
    }


def effective_schedule(policy: Policy) -> str:
    if policy.expires_at is not None:
        return schedule_name_for_policy(policy)
    return policy.schedule


def days_until_expiry(expires_at: date, *, today: date | None = None) -> int:
    ref = today or date.today()
    return (expires_at - ref).days


def alert_lead_days(policy: Policy, cfg: ExpiryConfig) -> tuple[int, ...]:
    if policy.alert_days_before is not None:
        return (policy.alert_days_before,)
    return cfg.alert_days_before


def policies_due_for_alert(
    policies: Iterable[Policy],
    cfg: ExpiryConfig,
    *,
    today: date | None = None,
) -> list[ExpiryAlert]:
    """Return policies that should trigger a Slack alert on ``today``."""
    ref = today or date.today()
    alerts: list[ExpiryAlert] = []
    for pol in policies:
        if pol.expires_at is None:
            continue
        remaining = days_until_expiry(pol.expires_at, today=ref)
        if remaining < 0:
            if remaining == -1:
                alerts.append(ExpiryAlert(pol, remaining, "expired"))
            continue
        if remaining == 0:
            alerts.append(ExpiryAlert(pol, remaining, "expires_today"))
            continue
        if remaining in alert_lead_days(pol, cfg):
            alerts.append(ExpiryAlert(pol, remaining, "warning"))
    return sorted(alerts, key=lambda a: (a.days_until, a.policy.name))


def expires_at_from_valid_days(valid_days: int, *, today: date | None = None) -> date:
    ref = today or date.today()
    return ref + timedelta(days=valid_days)
