from fwgitops.models import DesiredState, Policy, Service
from fwgitops.validator import validate

RULES = {
    "forbid_any": {"srcaddr": True, "dstaddr": True, "service": True},
    "allowed_interfaces": ["lan", "dmz"],
    "forbidden_ports": [23, 3389],
    "require": {"logtraffic": "all", "schedule": "always"},
    "max_changes_per_apply": 10,
}


def _policy(**kw) -> Policy:
    base = dict(
        name="p",
        srcintf=["lan"],
        dstintf=["dmz"],
        srcaddr=["corp"],
        dstaddr=["web"],
        service=["HTTPS"],
        action="accept",
        schedule="always",
        logtraffic="all",
        status="enable",
    )
    base.update(kw)
    return Policy(**base)


def test_valid_policy_passes():
    state = DesiredState(policies=[_policy()])
    assert validate(state, RULES) == []


def test_any_source_is_rejected():
    state = DesiredState(policies=[_policy(srcaddr=["all"])])
    errors = validate(state, RULES)
    assert any("srcaddr must not be" in e for e in errors)


def test_disallowed_interface_is_rejected():
    state = DesiredState(policies=[_policy(dstintf=["wan1"])])
    errors = validate(state, RULES)
    assert any("not in allowed_interfaces" in e for e in errors)


def test_missing_required_field_is_rejected():
    state = DesiredState(policies=[_policy(logtraffic="disable")])
    errors = validate(state, RULES)
    assert any("logtraffic must be 'all'" in e for e in errors)


def test_forbidden_port_via_custom_service_is_rejected():
    state = DesiredState(
        services=[Service(name="rdp", protocol="TCP", tcp_portrange="3389")],
        policies=[_policy(service=["rdp"])],
    )
    errors = validate(state, RULES)
    assert any("forbidden port" in e for e in errors)
