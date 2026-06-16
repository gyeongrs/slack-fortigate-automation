"""Post messages to Slack (usable from CI without running the Bolt app)."""

from __future__ import annotations

import os

import requests


class SlackPostError(RuntimeError):
    pass


def _resolve_channel(channel: str) -> str:
    channel = channel.strip()
    if channel.startswith("#"):
        return channel[1:]
    return channel


def post_message(
    text: str,
    *,
    blocks: list[dict] | None = None,
    channel: str | None = None,
    token: str | None = None,
) -> dict:
    token = token or os.environ.get("SLACK_BOT_TOKEN", "").strip()
    if not token:
        raise SlackPostError("SLACK_BOT_TOKEN is not set")

    channel = _resolve_channel(channel or os.getenv("SLACK_NOTIFY_CHANNEL", ""))
    if not channel:
        raise SlackPostError("SLACK_NOTIFY_CHANNEL is not set")

    payload: dict = {"channel": channel, "text": text}
    if blocks:
        payload["blocks"] = blocks

    resp = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise SlackPostError(data.get("error", "chat.postMessage failed"))
    return data
