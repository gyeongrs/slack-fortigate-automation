"""Machine-readable PR metadata and policy audit helpers."""

from __future__ import annotations

import json
import re
from typing import Any

META_MARKER = "<!-- fwgitops-meta:"
META_END = "-->"

_REQUIRED_LOG = "all"


def encode_meta(data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"{META_MARKER}{payload}{META_END}"


def decode_meta(body: str) -> dict[str, Any]:
    start = body.find(META_MARKER)
    if start == -1:
        return {}
    start += len(META_MARKER)
    end = body.find(META_END, start)
    if end == -1:
        return {}
    try:
        return json.loads(body[start:end])
    except json.JSONDecodeError:
        return {}


def parse_markdown_field(body: str, label: str) -> str:
    match = re.search(rf"\*\*{re.escape(label)}:\*\*\s*(.+)", body)
    return match.group(1).strip() if match else ""


def extract_policies_yaml(body: str) -> list[dict]:
    """Parse the policies block embedded in a PR body."""
    import yaml

    marker = "**Per-firewall policies:**"
    idx = body.find(marker)
    if idx == -1:
        return []
    fence = body.find("```yaml", idx)
    if fence == -1:
        return []
    start = body.find("\n", fence) + 1
    end = body.find("```", start)
    if end == -1:
        return []
    doc = yaml.safe_load(body[start:end]) or {}
    return doc.get("policies") or []


def check_logtraffic(policies: list[dict]) -> tuple[bool, list[str]]:
    """Return (all_enabled, list of issue strings)."""
    issues: list[str] = []
    for pol in policies:
        name = pol.get("name", "?")
        lt = pol.get("logtraffic")
        if lt != _REQUIRED_LOG:
            issues.append(
                f"`{name}`: logtraffic={lt!r} (required `{_REQUIRED_LOG}`)"
            )
    return not issues, issues


def logtraffic_summary(policies: list[dict]) -> str:
    ok, issues = check_logtraffic(policies)
    if not policies:
        return ":grey_question: No policies in request"
    if ok:
        return (
            f":white_check_mark: Traffic logging enabled on all {len(policies)} "
            f"policy/policies (`logtraffic: {_REQUIRED_LOG}`)"
        )
    return ":warning: Traffic logging issues:\n" + "\n".join(f"• {i}" for i in issues)
