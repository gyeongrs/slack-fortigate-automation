from fwgitops.models import Address, DesiredState, Policy, Service
from fwgitops.multi_device import state_for_device


def test_shared_services_on_every_device():
    state = DesiredState(
        services=[Service(name="app-https-8443", protocol="TCP", tcp_portrange="8443")],
        addresses=[Address(name="a", type="ipmask", subnet="10.0.0.1/32")],
        policies=[
            Policy(
                name="p-core",
                device="core-fw",
                srcintf=["core-trust"],
                dstintf=["core-untrust"],
                srcaddr=["a"],
                dstaddr=["a"],
                service=["app-https-8443"],
            ),
            Policy(
                name="p-ch",
                device="ch-fw",
                srcintf=["ch-trust"],
                dstintf=["ch-untrust"],
                srcaddr=["a"],
                dstaddr=["a"],
                service=["app-https-8443"],
            ),
        ],
    )
    for dev in ("core-fw", "ch-fw", "svr-fw"):
        scoped = state_for_device(state, dev)
        assert len(scoped.services) == 1
        assert scoped.services[0].name == "app-https-8443"
        assert len(scoped.addresses) == 1


def test_policies_filtered_by_device():
    state = DesiredState(
        policies=[
            Policy(
                name="only-core",
                device="core-fw",
                srcintf=["a"],
                dstintf=["b"],
                srcaddr=["x"],
                dstaddr=["y"],
                service=["HTTPS"],
            ),
            Policy(
                name="only-ch",
                device="ch-fw",
                srcintf=["a"],
                dstintf=["b"],
                srcaddr=["x"],
                dstaddr=["y"],
                service=["HTTPS"],
            ),
        ],
    )
    core = state_for_device(state, "core-fw")
    assert [p.name for p in core.policies] == ["only-core"]
    ch = state_for_device(state, "ch-fw")
    assert [p.name for p in ch.policies] == ["only-ch"]
