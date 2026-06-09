"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)  # .env wins over any stale shell/system env vars

# Marker comment so the engine only ever touches objects it created.
MANAGED_TAG = "managed-by:fwgitops"

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICIES_DIR = REPO_ROOT / "policies"
RULES_FILE = REPO_ROOT / "config" / "policy_rules.yaml"
# Custom services defined once here are pushed to every firewall (shared catalog).
SHARED_SERVICES_FILE = POLICIES_DIR / "services.yaml"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class FortiGateConfig:
    host: str
    api_token: str
    verify_tls: bool | str
    vdom: str | None
    dry_run: bool = False

    @property
    def base_url(self) -> str:
        return f"https://{self.host}/api/v2"

    @classmethod
    def from_env(cls) -> "FortiGateConfig":
        dry_run = _env_bool("FORTIGATE_DRY_RUN", False)
        host = os.getenv("FORTIGATE_HOST", "").strip()
        token = os.getenv("FORTIGATE_API_TOKEN", "").strip()
        if not dry_run and (not host or not token):
            raise RuntimeError(
                "FORTIGATE_HOST and FORTIGATE_API_TOKEN must be set "
                "(copy .env.example to .env), or set FORTIGATE_DRY_RUN=true "
                "to test without a device."
            )
        ca_bundle = os.getenv("FORTIGATE_CA_BUNDLE", "").strip()
        verify: bool | str = _env_bool("FORTIGATE_VERIFY_TLS", True)
        if ca_bundle:
            verify = ca_bundle
        vdom = os.getenv("FORTIGATE_VDOM", "").strip() or None
        return cls(
            host=host or "dry-run.local",
            api_token=token or "dry-run",
            verify_tls=verify,
            vdom=vdom,
            dry_run=dry_run,
        )

    @classmethod
    def from_device(cls, dev) -> "FortiGateConfig":
        """Build connection settings for one inventory device (``devices.yaml``)."""
        dry_run = _env_bool("FORTIGATE_DRY_RUN", False)
        token_env = dev.token_env or "FORTIGATE_API_TOKEN"
        token = os.getenv(token_env, "").strip()
        host = (dev.host or "").strip()
        if not dry_run and (not host or not token):
            raise RuntimeError(
                f"{dev.name}: set host in devices.yaml and "
                f"{token_env} in the environment (or FORTIGATE_DRY_RUN=true)."
            )
        ca_bundle = os.getenv("FORTIGATE_CA_BUNDLE", "").strip()
        verify: bool | str = _env_bool("FORTIGATE_VERIFY_TLS", True)
        if ca_bundle:
            verify = ca_bundle
        vdom = dev.vdom or os.getenv("FORTIGATE_VDOM", "").strip() or None
        return cls(
            host=host or "dry-run.local",
            api_token=token or "dry-run",
            verify_tls=verify,
            vdom=vdom,
            dry_run=dry_run,
        )
