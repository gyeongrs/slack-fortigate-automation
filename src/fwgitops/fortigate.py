"""Thin FortiOS REST API (CMDB) client.

Only covers the object types this tool manages: firewall address objects,
custom services, and firewall policies. Token auth via Bearer header.
"""

from __future__ import annotations

from typing import Any

import requests

from .config import FortiGateConfig


class FortiGateError(RuntimeError):
    pass


class FortiGateClient:
    def __init__(self, cfg: FortiGateConfig, timeout: float = 15.0) -> None:
        self._cfg = cfg
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {cfg.api_token}",
                "Content-Type": "application/json",
            }
        )
        self._session.verify = cfg.verify_tls

    # -- low level -------------------------------------------------------
    def _params(self, extra: dict | None = None) -> dict:
        params = dict(extra or {})
        if self._cfg.vdom:
            params["vdom"] = self._cfg.vdom
        return params

    def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        if self._cfg.dry_run:
            # No device available: reads return empty, writes are simulated.
            if method == "GET":
                return {"results": []}
            return {"dry_run": True}
        url = f"{self._cfg.base_url}/{path.lstrip('/')}"
        try:
            resp = self._session.request(
                method,
                url,
                params=self._params(kwargs.pop("params", None)),
                timeout=self._timeout,
                **kwargs,
            )
        except requests.RequestException as exc:  # network/TLS errors
            raise FortiGateError(f"{method} {path} failed: {exc}") from exc
        if resp.status_code >= 400:
            raise FortiGateError(
                f"{method} {path} -> HTTP {resp.status_code}: {resp.text}"
            )
        if resp.content:
            return resp.json()
        return {}

    # -- CMDB helpers ----------------------------------------------------
    def list_objects(self, endpoint: str) -> list[dict]:
        data = self._request("GET", f"cmdb/{endpoint}")
        return data.get("results", [])

    def create_object(self, endpoint: str, body: dict) -> dict:
        return self._request("POST", f"cmdb/{endpoint}", json=body)

    def update_object(self, endpoint: str, mkey: str, body: dict) -> dict:
        return self._request("PUT", f"cmdb/{endpoint}/{mkey}", json=body)

    def delete_object(self, endpoint: str, mkey: str) -> dict:
        return self._request("DELETE", f"cmdb/{endpoint}/{mkey}")

    # -- typed convenience ----------------------------------------------
    def get_addresses(self) -> dict[str, dict]:
        return {o["name"]: o for o in self.list_objects("firewall/address")}

    def get_services(self) -> dict[str, dict]:
        return {
            o["name"]: o
            for o in self.list_objects("firewall.service/custom")
        }

    def get_policies(self) -> dict[str, dict]:
        return {o["name"]: o for o in self.list_objects("firewall/policy")}
