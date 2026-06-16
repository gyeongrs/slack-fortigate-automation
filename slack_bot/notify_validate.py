"""Post PR validate/plan results to Slack (run from GitHub Actions validate workflow)."""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

from .messages import validate_result_blocks
from .pr_audit import fetch_pr_audit
from .slack_post import SlackPostError, post_message


def _read_log(path: str) -> str:
    if os.path.isfile(path):
        return open(path, encoding="utf-8", errors="replace").read()
    return ""


def main(argv: list[str] | None = None) -> int:
    load_dotenv(override=True)
    parser = argparse.ArgumentParser(
        description="Notify Slack after fwctl validate/plan on a pull request."
    )
    parser.add_argument(
        "--status",
        required=True,
        choices=("success", "failure"),
        help="Whether the validate step succeeded",
    )
    parser.add_argument(
        "--pr",
        type=int,
        default=None,
        help="Pull request number (default: GITHUB_EVENT pull_request.number)",
    )
    parser.add_argument(
        "--validate-log",
        default="validate.log",
        help="Path to fwctl validate stdout log",
    )
    parser.add_argument(
        "--plan-log",
        default="plan.log",
        help="Path to fwctl plan stdout log",
    )
    args = parser.parse_args(argv)

    pr_number = args.pr
    if pr_number is None:
        pr_number = int(os.getenv("GITHUB_EVENT_PULL_REQUEST_NUMBER", "0") or 0) or None

    audit = fetch_pr_audit(pr_number=pr_number)
    audit["status"] = args.status
    audit["validate_log"] = _read_log(args.validate_log)
    audit["plan_log"] = _read_log(args.plan_log)

    repo = os.getenv("GITHUB_REPOSITORY", "")
    run_id = os.getenv("GITHUB_RUN_ID", "")
    if repo and run_id:
        audit["workflow_url"] = f"https://github.com/{repo}/actions/runs/{run_id}"

    emoji = ":white_check_mark:" if args.status == "success" else ":x:"
    policy = audit.get("policy_name") or "firewall change"
    fallback = f"{emoji} PR validation {args.status}: {policy}"

    try:
        post_message(fallback, blocks=validate_result_blocks(audit))
    except SlackPostError as exc:
        print(f"Slack notification failed: {exc}", file=sys.stderr)
        return 1

    print("Slack validation notification sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
