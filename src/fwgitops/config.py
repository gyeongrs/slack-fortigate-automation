"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Marker comment so the engine only ever touches objects it created.
MANAGED_TAG = "managed-by:fwgitops"

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICIES_DIR = REPO_ROOT / "policies"
RULES_FILE = REPO_ROOT / "config" / "policy_rules.yaml"


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

    @property
    def base_url(self) -> str:
        return f"https://{self.host}/api/v2"

    @classmethod
    def from_env(cls) -> "FortiGateConfig":
        host = os.getenv("FORTIGATE_HOST", "").strip()
        token = os.getenv("FORTIGATE_API_TOKEN", "").strip()
        if not host or not token:
            raise RuntimeError(
                "FORTIGATE_HOST and FORTIGATE_API_TOKEN must be set "
                "(copy .env.example to .env)."
            )
        ca_bundle = os.getenv("FORTIGATE_CA_BUNDLE", "").strip()
        verify: bool | str = _env_bool("FORTIGATE_VERIFY_TLS", True)
        if ca_bundle:
            verify = ca_bundle
        vdom = os.getenv("FORTIGATE_VDOM", "").strip() or None
        return cls(host=host, api_token=token, verify_tls=verify, vdom=vdom)
