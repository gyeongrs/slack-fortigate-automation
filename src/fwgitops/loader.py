"""Load and parse the desired-state YAML files into typed models."""

from __future__ import annotations

from pathlib import Path

import yaml

from .config import POLICIES_DIR, RULES_FILE, SHARED_SERVICES_FILE
from .models import Address, DesiredState, Policy, Service


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_desired_state(policies_dir: Path | None = None) -> DesiredState:
    base = policies_dir or POLICIES_DIR
    addresses = _read_yaml(base / "addresses.yaml").get("addresses", [])
    services = load_shared_services(base)
    policies = _read_yaml(base / "firewall_policies.yaml").get("policies", [])

    return DesiredState(
        addresses=[Address(**a) for a in addresses],
        services=[Service(**s) for s in services],
        policies=[Policy(**p) for p in policies],
    )


def load_shared_services(policies_dir: Path | None = None) -> list[dict]:
    """Return the global service catalog (same objects on every firewall)."""
    base = policies_dir or POLICIES_DIR
    path = base / "services.yaml"
    if not path.exists() and SHARED_SERVICES_FILE.exists():
        path = SHARED_SERVICES_FILE
    return _read_yaml(path).get("services", [])


def load_rules(rules_file: Path | None = None) -> dict:
    return _read_yaml(rules_file or RULES_FILE)
