"""Post FortiGate apply results to Slack (run from GitHub Actions)."""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

from .messages import apply_result_blocks
from .pr_audit import fetch_pr_audit, parse_apply_log
from .slack_post import SlackPostError, post_message


def main(argv: list[str] | None = None) -> int:
    load_dotenv(override=True)
    parser = argparse.ArgumentParser(description="Notify Slack after fwctl apply.")
    parser.add_argument(
        "--log",
        default="apply.log",
        help="Path to fwctl apply stdout log (default: apply.log)",
    )
    parser.add_argument(
        "--status",
        required=True,
        choices=("success", "failure"),
        help="Whether the apply step succeeded",
    )
    parser.add_argument(
        "--commit-sha",
        default=os.getenv("GITHUB_SHA", ""),
        help="Merge commit SHA (default: GITHUB_SHA env)",
    )
    parser.add_argument(
        "--pr",
        type=int,
        default=None,
        help="PR number (optional; resolved from commit if omitted)",
    )
    args = parser.parse_args(argv)

    apply_log = ""
    if os.path.isfile(args.log):
        apply_log = open(args.log, encoding="utf-8", errors="replace").read()

    audit = fetch_pr_audit(pr_number=args.pr, commit_sha=args.commit_sha or None)
    audit["status"] = args.status
    audit["apply_log"] = apply_log
    audit["apply_actions"] = parse_apply_log(apply_log)

    repo = os.getenv("GITHUB_REPOSITORY", "")
    run_id = os.getenv("GITHUB_RUN_ID", "")
    if repo and run_id:
        audit["workflow_url"] = (
            f"https://github.com/{repo}/actions/runs/{run_id}"
        )

    emoji = ":white_check_mark:" if args.status == "success" else ":x:"
    policy = audit.get("policy_name") or "firewall change"
    fallback = f"{emoji} FortiGate apply {args.status}: {policy}"

    try:
        post_message(fallback, blocks=apply_result_blocks(audit))
    except SlackPostError as exc:
        print(f"Slack notification failed: {exc}", file=sys.stderr)
        return 1

    print("Slack notification sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
