"""Slack Block Kit builders for firewall request / apply summaries."""

from __future__ import annotations

from typing import Any

from .metadata import logtraffic_summary


def _truncate(text: str, limit: int = 2800) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n… _(truncated)_"


def _join_field(values: list[str]) -> str:
    return ">".join(values) if values else "?"


def _format_policy_line(p: dict, default_expiry: str | None) -> str:
    exp = p.get("expires_at") or default_expiry or "?"
    src = _join_field(p.get("srcaddr") or [])
    dst = _join_field(p.get("dstaddr") or [])
    svc = ",".join(p.get("service") or [])
    log = p.get("logtraffic") or "?"
    device = p.get("device") or "?"
    return (
        f"• {p.get('name', '?')} ({device}) | {src}>{dst} | {svc} | "
        f"log: {log} | until {exp}"
    )


def _format_target_fw_lines(targets: list[dict]) -> str:
    lines = []
    for t in targets:
        lines.append(
            f"• {t['device']}: srcintf {t['srcintf']}, dstintf {t['dstintf']}"
        )
    return "\n".join(lines) or "_none_"


def request_summary_blocks(
    *,
    policy_name: str,
    requester_id: str,
    requester_name: str,
    requester_real_name: str = "",
    team_name: str = "",
    justification: str,
    pr: dict,
    policies: list[dict],
    targets: list[dict] | None = None,
    new_addresses: list[dict] | None = None,
    new_services: list[dict] | None = None,
    expires_at: str | None = None,
) -> list[dict]:
    """Approval message layout (PR summary + Target FW + action buttons)."""
    devices = ", ".join(p.get("device") or "?" for p in policies)
    display_name = requester_real_name or requester_name
    team = team_name or "—"

    policy_text = "\n".join(
        _format_policy_line(p, expires_at) for p in policies
    ) or "_none_"

    target_fw = _format_target_fw_lines(targets or [])
    expiry_line = f"Policy expiry: {expires_at}" if expires_at else ""

    body = (
        f"*PR:*\n"
        f"<{pr['url']}|#{pr['number']}>\n\n"
        f"*Requester:*\n"
        f"{display_name} ({requester_name}) ({team})\n\n"
        f"*Commnets:*\n"
        f"{justification or '_(none)_'}\n\n"
        f"*Firewalls:*\n"
        f"{devices}\n\n"
    )
    if expiry_line:
        body += f"{expiry_line}\n\n"
    body += f"*Policies ({len(policies)}):*\n{policy_text}\n\n*Target FW*\n{target_fw}"

    extras: list[str] = []
    if new_addresses:
        parts = [
            f"{a['name']} ({a.get('subnet') or a.get('fqdn', '?')}"
            f"{', zone=' + a['zone'] if a.get('zone') else ''})"
            for a in new_addresses
        ]
        extras.append(f"*New addresses:* {', '.join(parts)}")
    if new_services:
        parts = []
        for s in new_services:
            port = s.get("tcp_portrange") or s.get("udp_portrange") or "?"
            parts.append(f"{s['name']} ({s.get('protocol', '?')} {port})")
        extras.append(f"*New services:* {', '.join(parts)}")
    if extras:
        body += "\n\n" + "\n".join(extras)

    blocks: list[dict] = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": body},
        },
    ]

    blocks.append({"type": "divider"})
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        "_Another team member must approve (not the requester). "
                        "CI validates guardrails; `@gyeongrs/netops` CODEOWNERS "
                        "review is required on GitHub before merge._"
                    ),
                }
            ],
        }
    )

    payload = {
        "pr": pr["number"],
        "requester": requester_id,
        "name": policy_name,
    }
    import json

    blocks.append(
        {
            "type": "actions",
            "block_id": "fw_approval",
            "elements": [
                {
                    "type": "button",
                    "style": "primary",
                    "text": {"type": "plain_text", "text": "Approve & merge"},
                    "action_id": "approve_request",
                    "value": json.dumps(payload),
                    "confirm": {
                        "title": {"type": "plain_text", "text": "Approve?"},
                        "text": {
                            "type": "plain_text",
                            "text": f"Merge PR #{pr['number']} and apply '{policy_name}'?",
                        },
                        "confirm": {"type": "plain_text", "text": "Approve"},
                        "deny": {"type": "plain_text", "text": "Cancel"},
                    },
                },
                {
                    "type": "button",
                    "style": "danger",
                    "text": {"type": "plain_text", "text": "Reject"},
                    "action_id": "reject_request",
                    "value": json.dumps(payload),
                },
            ],
        }
    )
    return blocks


def address_summary_blocks(
    *,
    summary_name: str,
    requester_id: str,
    requester_name: str,
    requester_real_name: str = "",
    team_name: str = "",
    justification: str,
    pr: dict,
    new_addresses: list[dict],
) -> list[dict]:
    """Approval message for address-only PRs."""
    display_name = requester_real_name or requester_name
    team = team_name or "—"

    addr_lines = []
    for a in new_addresses:
        exp = a.get("expires_at") or "—"
        zone = a.get("zone") or "?"
        subnet = a.get("subnet") or a.get("fqdn") or "?"
        addr_lines.append(
            f"• `{a.get('name', '?')}` {subnet} | zone: {zone} | until {exp}"
        )
    addr_text = "\n".join(addr_lines) or "_none_"

    body = (
        f"*PR:*\n"
        f"<{pr['url']}|#{pr['number']}>\n\n"
        f"*Requester:*\n"
        f"{display_name} ({requester_name}) ({team})\n\n"
        f"*Comments:*\n"
        f"{justification or '_(none)_'}\n\n"
        f"*Address objects ({len(new_addresses)}):*\n{addr_text}"
    )

    import json

    payload = {
        "pr": pr["number"],
        "requester": requester_id,
        "name": summary_name,
    }

    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": body}},
        {"type": "divider"},
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        "_Another team member must approve (not the requester). "
                        "CI validates guardrails; `@gyeongrs/netops` CODEOWNERS "
                        "review is required on GitHub before merge._"
                    ),
                }
            ],
        },
        {
            "type": "actions",
            "block_id": "fw_approval",
            "elements": [
                {
                    "type": "button",
                    "style": "primary",
                    "text": {"type": "plain_text", "text": "Approve & merge"},
                    "action_id": "approve_request",
                    "value": json.dumps(payload),
                    "confirm": {
                        "title": {"type": "plain_text", "text": "Approve?"},
                        "text": {
                            "type": "plain_text",
                            "text": f"Merge PR #{pr['number']} and add address(es)?",
                        },
                        "confirm": {"type": "plain_text", "text": "Approve"},
                        "deny": {"type": "plain_text", "text": "Cancel"},
                    },
                },
                {
                    "type": "button",
                    "style": "danger",
                    "text": {"type": "plain_text", "text": "Reject"},
                    "action_id": "reject_request",
                    "value": json.dumps(payload),
                },
            ],
        },
    ]


def validate_result_blocks(audit: dict[str, Any]) -> list[dict]:
    """Summary after fwctl validate/plan in CI (pull_request workflow)."""
    success = audit.get("status") == "success"
    emoji = ":white_check_mark:" if success else ":x:"
    title = "PR validation passed" if success else "PR validation FAILED"

    requester = audit.get("requester", "?")
    requester_slack = audit.get("requester_slack_id")
    if requester_slack:
        requester_display = f"<@{requester_slack}> (`{requester}`)"
    else:
        requester_display = f"`{requester}`"

    pr_num = audit.get("pr_number")
    pr_url = audit.get("pr_url", "")
    pr_line = f"<{pr_url}|PR #{pr_num}>" if pr_url and pr_num else "_(no linked PR)_"

    validate_log = _truncate(audit.get("validate_log") or "_(empty)_", 1200)
    plan_log = _truncate(audit.get("plan_log") or "_(empty)_", 1200)
    policies = audit.get("policies") or []
    log_line = logtraffic_summary(policies)

    next_step = (
        ":busts_in_silhouette: Waiting for `@gyeongrs/netops` CODEOWNERS approval "
        "on GitHub, then Slack *Approve & merge*."
        if success
        else ":wrench: Fix validation errors and push to the PR branch."
    )

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{emoji} {title}"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Policy:*\n{audit.get('policy_name', '?')}"},
                {"type": "mrkdwn", "text": f"*PR:*\n{pr_line}"},
                {"type": "mrkdwn", "text": f"*Requester:*\n{requester_display}"},
                {
                    "type": "mrkdwn",
                    "text": f"*Justification:*\n{audit.get('justification') or '_(none)_'}",
                },
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Traffic logging (request):*\n{log_line}"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Validate log:*\n```{validate_log}```"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Plan preview:*\n```{plan_log}```"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Next step:*\n{next_step}"},
        },
    ]

    if audit.get("workflow_url"):
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"<{audit['workflow_url']}|View GitHub Actions run>",
                    }
                ],
            }
        )
    return blocks


def apply_result_blocks(audit: dict[str, Any]) -> list[dict]:
    """Summary after fwctl apply in CI."""
    success = audit.get("status") == "success"
    emoji = ":white_check_mark:" if success else ":x:"
    title = "FortiGate apply succeeded" if success else "FortiGate apply FAILED"

    requester = audit.get("requester", "?")
    requester_slack = audit.get("requester_slack_id")
    if requester_slack:
        requester_display = f"<@{requester_slack}> (`{requester}`)"
    else:
        requester_display = f"`{requester}`"

    approver = audit.get("approver", "?")
    approver_slack = audit.get("approver_slack_id")
    if approver_slack:
        approver_display = f"<@{approver_slack}> (`{approver}`)"
    elif approver and approver != "?":
        approver_display = f"`{approver}`"
    else:
        approver_display = "_(unknown)_"

    pr_num = audit.get("pr_number")
    pr_url = audit.get("pr_url", "")
    pr_line = f"<{pr_url}|PR #{pr_num}>" if pr_url and pr_num else "_(no linked PR)_"

    commit_sha = audit.get("commit_sha", "")[:12]
    commit_url = audit.get("commit_url", "")
    commit_line = (
        f"<{commit_url}|`{commit_sha}`>" if commit_url else f"`{commit_sha}`"
    )

    files = audit.get("changed_files") or []
    files_text = "\n".join(f"• `{f}`" for f in files) or "_(none)_"

    commits = audit.get("commits") or []
    commit_lines = []
    for c in commits[:8]:
        sha = (c.get("sha") or "")[:7]
        msg = (c.get("message") or "").split("\n")[0][:80]
        commit_lines.append(f"• `{sha}` {msg}")
    commits_text = "\n".join(commit_lines) or "_(none)_"

    apply_log = _truncate(audit.get("apply_log") or "_(empty)_", 1500)
    policies = audit.get("policies") or []
    log_line = logtraffic_summary(policies)

    apply_actions = audit.get("apply_actions") or []
    actions_text = "\n".join(f"• {a}" for a in apply_actions[:20]) or "_(no changes)_"
    if len(apply_actions) > 20:
        actions_text += f"\n_…and {len(apply_actions) - 20} more_"

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{emoji} {title}"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Policy:*\n{audit.get('policy_name', '?')}"},
                {"type": "mrkdwn", "text": f"*PR:*\n{pr_line}"},
                {"type": "mrkdwn", "text": f"*Requester:*\n{requester_display}"},
                {"type": "mrkdwn", "text": f"*Approver:*\n{approver_display}"},
                {"type": "mrkdwn", "text": f"*Justification:*\n{audit.get('justification') or '_(none)_'}"},
                {"type": "mrkdwn", "text": f"*Merge commit:*\n{commit_line}"},
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Traffic logging (apply):*\n{log_line}",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Changed files:*\n{files_text}",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*PR commits:*\n{commits_text}",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Apply actions:*\n{actions_text}",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Apply log:*\n```{apply_log}```",
            },
        },
    ]

    if audit.get("workflow_url"):
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"<{audit['workflow_url']}|View GitHub Actions run>",
                    }
                ],
            }
        )
    return blocks
