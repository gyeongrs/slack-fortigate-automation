from datetime import date, timedelta

from fwgitops.expiry import (
    ExpiryConfig,
    effective_schedule,
    expires_at_from_valid_days,
    load_expiry_config,
    policies_due_for_alert,
    schedule_body,
    schedule_name_for_policy,
)
from fwgitops.models import Policy
from fwgitops.validator import validate
from fwgitops.models import Address, DesiredState

RULES = {
    "forbid_any": {"srcaddr": True, "dstaddr": True, "service": True},
    "allowed_interfaces": ["lan", "dmz"],
    "forbidden_ports": [],
    "allowed_builtin_services": ["HTTPS"],
    "require": {"logtraffic": "all", "schedule": "always"},
    "expiry": {
        "default_valid_days": 90,
        "alert_days_before": [14, 7, 1],
        "max_valid_days": 365,
    },
}

_ADDRESSES = [
    Address(name="corp", type="ipmask", subnet="10.20.0.0/16"),
    Address(name="web", type="ipmask", subnet="10.10.20.15/32"),
]


def _policy(**kw) -> Policy:
    base = dict(
        name="temp-rule",
        srcintf=["lan"],
        dstintf=["dmz"],
        srcaddr=["corp"],
        dstaddr=["web"],
        service=["HTTPS"],
        expires_at=date.today() + timedelta(days=30),
    )
    base.update(kw)
    return Policy(**base)


def test_load_expiry_config():
    cfg = load_expiry_config(RULES)
    assert cfg.default_valid_days == 90
    assert cfg.alert_days_before == (14, 7, 1)


def test_schedule_name_and_body():
    pol = _policy(name="allow-web-test")
    assert schedule_name_for_policy(pol).startswith("fwgitops-")
    body = schedule_body(pol, start=date(2026, 1, 1))
    assert body["start-date"] == "2026-01-01"
    assert body["end-date"] == pol.expires_at.isoformat()


def test_effective_schedule_uses_generated_name():
    pol = _policy()
    assert effective_schedule(pol) == schedule_name_for_policy(pol)
    pol_permanent = _policy(expires_at=None, schedule="always")
    assert effective_schedule(pol_permanent) == "always"


def test_policies_due_for_alert_on_lead_days():
    today = date(2026, 6, 1)
    cfg = ExpiryConfig(alert_days_before=(14, 7, 1))
    pol = _policy(expires_at=today + timedelta(days=7))
    alerts = policies_due_for_alert([pol], cfg, today=today)
    assert len(alerts) == 1
    assert alerts[0].kind == "warning"
    assert alerts[0].days_until == 7


def test_policies_due_for_alert_expires_today():
    today = date(2026, 6, 1)
    pol = _policy(expires_at=today)
    alerts = policies_due_for_alert([pol], ExpiryConfig(), today=today)
    assert len(alerts) == 1
    assert alerts[0].kind == "expires_today"


def test_expires_at_skips_schedule_require():
    pol = _policy(schedule="always", expires_at=date.today() + timedelta(days=10))
    state = DesiredState(addresses=list(_ADDRESSES), policies=[pol])
    assert validate(state, RULES) == []


def test_past_expires_at_is_rejected():
    pol = _policy(expires_at=date.today() - timedelta(days=1))
    state = DesiredState(addresses=list(_ADDRESSES), policies=[pol])
    errors = validate(state, RULES)
    assert any("in the past" in e for e in errors)


def test_expires_at_from_valid_days():
    today = date(2026, 6, 1)
    exp = expires_at_from_valid_days(90, today=today)
    assert exp == date(2026, 8, 30)
