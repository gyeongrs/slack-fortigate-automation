"""Quick Slack connectivity check before running the bot.

Usage (from repo root, venv active):

    python -m slack_bot.check_slack
    python -m slack_bot.check_slack --post   # also post a test message
"""

from __future__ import annotations

import argparse
import os
import sys

import requests
from dotenv import load_dotenv


def _mask(token: str) -> str:
    token = token.strip()
    if len(token) <= 12:
        return "***"
    return f"{token[:8]}...{token[-4:]}"


def _check(name: str, ok: bool, detail: str = "") -> bool:
    mark = "OK" if ok else "FAIL"
    line = f"[{mark}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Slack tokens and channel access.")
    parser.add_argument(
        "--post",
        action="store_true",
        help="Post a test message to SLACK_NOTIFY_CHANNEL",
    )
    args = parser.parse_args()

    load_dotenv(override=True)

    bot = os.getenv("SLACK_BOT_TOKEN", "").strip()
    app = os.getenv("SLACK_APP_TOKEN", "").strip()
    secret = os.getenv("SLACK_SIGNING_SECRET", "").strip()
    channel = os.getenv("SLACK_NOTIFY_CHANNEL", "").strip()

    print("Slack preflight\n")

    ok = True
    ok &= _check("SLACK_BOT_TOKEN set", bool(bot), _mask(bot) if bot else "missing")
    ok &= _check(
        "SLACK_APP_TOKEN set",
        bool(app),
        _mask(app) if app else "missing (required for Socket Mode bot)",
    )
    ok &= _check("SLACK_SIGNING_SECRET set", bool(secret), "set" if secret else "missing")
    ok &= _check(
        "SLACK_NOTIFY_CHANNEL set",
        bool(channel),
        channel or "missing (use #channel-name or channel ID)",
    )

    if not bot:
        print("\nCopy .env.example to .env and fill in Slack tokens.")
        return 1

    resp = requests.get(
        "https://slack.com/api/auth.test",
        headers={"Authorization": f"Bearer {bot}"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("ok"):
        ok &= _check(
            "auth.test",
            True,
            f"team={data.get('team')} bot={data.get('user')}",
        )
    else:
        ok &= _check("auth.test", False, data.get("error", "unknown error"))

    if args.post:
        if not channel:
            ok &= _check("chat.postMessage", False, "SLACK_NOTIFY_CHANNEL not set")
        else:
            ch = channel.lstrip("#")
            post = requests.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {bot}"},
                json={
                    "channel": ch,
                    "text": ":white_check_mark: fwgitops Slack check — bot can post here.",
                },
                timeout=30,
            )
            post.raise_for_status()
            pdata = post.json()
            if pdata.get("ok"):
                ok &= _check("chat.postMessage", True, f"channel={ch}")
            else:
                err = pdata.get("error", "failed")
                hint = ""
                if err == "not_in_channel":
                    hint = " — invite the bot to the channel: /invite @YourBotName"
                ok &= _check("chat.postMessage", False, err + hint)

    print()
    if ok:
        print("All checks passed. Start the bot with:")
        print("  python -m slack_bot.app")
        print("Then in Slack run: /fw-policy")
        return 0

    print("Fix the failures above, then re-run this script.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
