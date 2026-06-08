from fwgitops.applier import apply_plan
from fwgitops.config import FortiGateConfig
from fwgitops.fortigate import FortiGateClient
from fwgitops.models import Address, DesiredState, Policy
from fwgitops.planner import build_plan


def _client() -> FortiGateClient:
    cfg = FortiGateConfig(
        host="dry-run.local",
        api_token="dry-run",
        verify_tls=False,
        vdom=None,
        dry_run=True,
    )
    return FortiGateClient(cfg)


def test_dry_run_reads_return_empty():
    client = _client()
    assert client.get_addresses() == {}
    assert client.get_services() == {}
    assert client.get_policies() == {}


def test_dry_run_plan_is_all_create_and_apply_succeeds():
    state = DesiredState(
        addresses=[Address(name="a", type="ipmask", subnet="10.0.0.1/32")],
        policies=[
            Policy(
                name="p",
                srcintf=["lan"],
                dstintf=["dmz"],
                srcaddr=["a"],
                dstaddr=["a"],
                service=["HTTPS"],
            )
        ],
    )
    client = _client()
    plan = build_plan(state, client)
    assert plan.items and all(i.action == "create" for i in plan.items)

    log = apply_plan(plan, client)
    assert any("[created]" in line for line in log)
    assert not any("[ERROR]" in line for line in log)
