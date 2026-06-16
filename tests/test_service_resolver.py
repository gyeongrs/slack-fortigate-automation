from fwgitops.service_resolver import resolve_services

_CATALOG = [
    {"name": "app-https-8443", "protocol": "TCP", "tcp_portrange": "8443"},
]
_BUILTINS = {"HTTPS", "HTTP", "SSH", "DNS"}


def test_existing_service_name():
    names, new, bad = resolve_services(
        ["app-https-8443"], _CATALOG, _BUILTINS, autocreate=True
    )
    assert names == ["app-https-8443"]
    assert new == []
    assert bad == []


def test_builtin_service():
    names, new, bad = resolve_services(["https"], _CATALOG, _BUILTINS, autocreate=True)
    assert names == ["HTTPS"]
    assert new == []


def test_autocreate_from_bare_port():
    names, new, bad = resolve_services(["9000"], _CATALOG, _BUILTINS, autocreate=True)
    assert names == ["auto-tcp-9000"]
    assert len(new) == 1
    assert new[0]["tcp_portrange"] == "9000"
    assert bad == []


def test_autocreate_from_tcp_slash_port():
    names, new, bad = resolve_services(
        ["tcp/7777"], _CATALOG, _BUILTINS, autocreate=True
    )
    assert names == ["auto-tcp-7777"]
    assert new[0]["protocol"] == "TCP"


def test_autocreate_named_service():
    names, new, bad = resolve_services(
        ["my-app=tcp/8443"], _CATALOG, _BUILTINS, autocreate=True
    )
    assert names == ["my-app"]
    assert new[0]["name"] == "my-app"
    assert new[0]["tcp_portrange"] == "8443"


def test_unknown_service_without_autocreate():
    names, new, bad = resolve_services(["unknown-svc"], _CATALOG, _BUILTINS)
    assert names == []
    assert bad == ["unknown-svc"]


def test_forbidden_port_still_resolves_then_validator_catches():
    names, new, bad = resolve_services(["3389"], _CATALOG, _BUILTINS, autocreate=True)
    assert names == ["auto-tcp-3389"]
    assert len(new) == 1
