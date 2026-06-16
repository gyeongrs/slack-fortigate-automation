"""Post policy expiry warnings to Slack (daily GitHub Actions cron)."""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

from fwgitops.expiry import load_expiry_config, policies_due_for_alert
from fwgitops.loader import load_desired_state, load_rules

from .slack_post import SlackPostError, post_message


def _requester_line(policy) -> str:
    sid = policy.requester_slack_id
    user = policy.requester
    if sid:
        suffix = f" (`{user}`)" if user else ""
        return f"<@{sid}>{suffix}"
    if user:
        return f"`{user}`"
    return "_(unknown)_"


def _alert_line(alert) -> str:
    pol = alert.policy
    device = pol.device or "default"
    base = (
        f"• `{pol.name}` on *{device}* — expires `{pol.expires_at}` "
        f"({pol.srcaddr} → {pol.dstaddr}) | requester: {_requester_line(pol)}"
    )
    if alert.kind == "warning":
        return f":warning: {base} — *{alert.days_until} day(s) remaining*"
    if alert.kind == "expires_today":
        return f":hourglass: {base} — *expires today*"
    return f":no_entry: {base} — *expired yesterday* (remove or extend in git)"


def expiry_alert_blocks(alerts) -> list[dict]:
    lines = [_alert_line(a) for a in alerts]
    body = "\n".join(lines)
    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Firewall policy expiry notice"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{len(alerts)} temporary polic"
                    f"{'y' if len(alerts) == 1 else 'ies'} need attention:\n\n"
                    f"{body}"
                ),
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        "_Policies with `expires_at` stop on the FortiGate schedule "
                        "after the end date. Remove or extend them in "
                        "`policies/firewall_policies.yaml`._"
                    ),
                }
            ],
        },
    ]


def main(argv: list[str] | None = None) -> int:
    load_dotenv(override=True)
    parser = argparse.ArgumentParser(
        description="Notify Slack about upcoming policy expirations."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print alerts to stdout without posting to Slack",
    )
    args = parser.parse_args(argv)

    state = load_desired_state()
    rules = load_rules()
    cfg = load_expiry_config(rules)
    alerts = policies_due_for_alert(state.policies, cfg)

    if not alerts:
        print("No expiry alerts due today.")
        return 0

    fallback = f":hourglass: {len(alerts)} firewall policy expiry notice(s)"
    if args.dry_run:
        for line in [_alert_line(a) for a in alerts]:
            print(line)
        return 0

    try:
        post_message(fallback, blocks=expiry_alert_blocks(alerts))
    except SlackPostError as exc:
        print(f"Slack notification failed: {exc}", file=sys.stderr)
        return 1

    print(f"Posted {len(alerts)} expiry alert(s) to Slack.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
