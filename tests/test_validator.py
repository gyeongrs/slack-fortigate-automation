from fwgitops.models import Address, DesiredState, Policy, Service
from fwgitops.validator import validate

RULES = {
    "forbid_any": {"srcaddr": True, "dstaddr": True, "service": True},
    "allowed_interfaces": ["lan", "dmz"],
    "forbidden_ports": [23, 3389],
    "allowed_builtin_services": ["HTTPS", "HTTP", "DNS"],
    "require": {"logtraffic": "all", "schedule": "always"},
    "max_changes_per_apply": 10,
}

# Address objects referenced by the default test policy.
_ADDRESSES = [
    Address(name="corp", type="ipmask", subnet="10.20.0.0/16"),
    Address(name="web", type="ipmask", subnet="10.10.20.15/32"),
]


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


def _state(policies, services=None) -> DesiredState:
    return DesiredState(
        addresses=list(_ADDRESSES),
        services=services or [],
        policies=policies,
    )


def test_valid_policy_passes():
    assert validate(_state([_policy()]), RULES) == []


def test_any_source_is_rejected():
    errors = validate(_state([_policy(srcaddr=["all"])]), RULES)
    assert any("srcaddr must not be" in e for e in errors)


def test_disallowed_interface_is_rejected():
    errors = validate(_state([_policy(dstintf=["wan1"])]), RULES)
    assert any("not in allowed_interfaces" in e for e in errors)


def test_missing_required_field_is_rejected():
    errors = validate(_state([_policy(logtraffic="disable")]), RULES)
    assert any("logtraffic must be 'all'" in e for e in errors)


def test_forbidden_port_via_custom_service_is_rejected():
    svc = [Service(name="rdp", protocol="TCP", tcp_portrange="3389")]
    errors = validate(_state([_policy(service=["rdp"])], services=svc), RULES)
    assert any("forbidden port" in e for e in errors)


def test_undefined_address_is_rejected():
    errors = validate(_state([_policy(dstaddr=["ghost-host"])]), RULES)
    assert any("'ghost-host' is not defined" in e for e in errors)


def test_undefined_service_is_rejected():
    errors = validate(_state([_policy(service=["made-up-svc"])]), RULES)
    assert any("'made-up-svc' is neither" in e for e in errors)


def test_duplicate_policy_name_is_rejected():
    errors = validate(_state([_policy(name="dup"), _policy(name="dup")]), RULES)
    assert any("duplicate policy name 'dup'" in e for e in errors)


def test_same_policy_name_on_different_devices_is_ok():
    errors = validate(
        _state(
            [
                _policy(name="dc1svr-10.56.10.10>dc1ch-10.51.10.1", device="dc1-svr-fw"),
                _policy(name="dc1svr-10.56.10.10>dc1ch-10.51.10.1", device="dc1-ch-fw"),
            ]
        ),
        RULES,
    )
    assert not any("duplicate policy" in e for e in errors)
