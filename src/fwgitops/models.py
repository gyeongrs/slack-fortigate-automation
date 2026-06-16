"""Pydantic models describing the desired state of FortiGate objects."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Address(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: Literal["ipmask", "iprange", "fqdn"] = "ipmask"
    subnet: str | None = None          # for type=ipmask, e.g. "10.0.0.1/32"
    start_ip: str | None = None        # for type=iprange
    end_ip: str | None = None          # for type=iprange
    fqdn: str | None = None            # for type=fqdn
    comment: str = ""
    center: str | None = None          # GitOps only — site (e.g. dc1); not sent to FortiGate
    zone: str | None = None            # GitOps only — security zone; see policy_rules zone_map
    expires_at: date | None = None     # GitOps only — last valid day for this object


class Service(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    protocol: Literal["TCP", "UDP", "TCP/UDP/SCTP"] = "TCP"
    tcp_portrange: str | None = None   # e.g. "8443" or "8000-8100"
    udp_portrange: str | None = None
    comment: str = ""


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    device: str | None = None  # target firewall (route-selected); None = default
    srcintf: list[str]
    dstintf: list[str]
    srcaddr: list[str]
    dstaddr: list[str]
    service: list[str]
    action: Literal["accept", "deny"] = "accept"
    schedule: str = "always"
    logtraffic: Literal["all", "utm", "disable"] = "all"
    status: Literal["enable", "disable"] = "enable"
    nat: bool = False
    comment: str = ""
    expires_at: date | None = None  # last valid day (inclusive); auto schedule on device
    requester: str | None = None  # Slack username (for expiry alerts)
    requester_slack_id: str | None = None  # Slack user id to @mention in alerts
    alert_days_before: int | None = None  # override global alert lead time (days)


class DesiredState(BaseModel):
    addresses: list[Address] = Field(default_factory=list)
    services: list[Service] = Field(default_factory=list)
    policies: list[Policy] = Field(default_factory=list)
