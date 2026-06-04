"""Slack entrypoint: `/fw-request` opens a modal, submission opens a PR.

Run with:
    uvicorn slack_bot.app:api --port 3000

Slack app config:
    - Slash command  /fw-request  ->  https://<host>/slack/events
    - Interactivity request URL    ->  https://<host>/slack/events
    Scopes: commands, chat:write
"""

from __future__ import annotations

import json
import os

from fastapi import FastAPI, Request
from slack_bolt import App
from slack_bolt.adapter.fastapi import SlackRequestHandler

from .github_pr import open_policy_pr

app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
)
handler = SlackRequestHandler(app)
api = FastAPI()


def _modal() -> dict:
    def text_input(block_id: str, label: str, placeholder: str) -> dict:
        return {
            "type": "input",
            "block_id": block_id,
            "label": {"type": "plain_text", "text": label},
            "element": {
                "type": "plain_text_input",
                "action_id": "value",
                "placeholder": {"type": "plain_text", "text": placeholder},
            },
        }

    return {
        "type": "modal",
        "callback_id": "fw_request_submit",
        "title": {"type": "plain_text", "text": "Firewall Request"},
        "submit": {"type": "plain_text", "text": "Open PR"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            text_input("name", "Policy name", "allow-corp-to-app"),
            text_input("srcintf", "Source interface(s)", "lan"),
            text_input("dstintf", "Dest interface(s)", "dmz"),
            text_input("srcaddr", "Source address object(s)", "corp-clients"),
            text_input("dstaddr", "Dest address object(s)", "app-web-server"),
            text_input("service", "Service(s)", "HTTPS, app-https-8443"),
            text_input("justification", "Justification / ticket", "NETOPS-1001"),
        ],
    }


@app.command("/fw-request")
def open_request_modal(ack, body, client):
    ack()
    client.views_open(trigger_id=body["trigger_id"], view=_modal())


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.replace(",", " ").split() if v.strip()]


@app.view("fw_request_submit")
def handle_submission(ack, body, view, client):
    ack()
    values = view["state"]["values"]

    def field(block_id: str) -> str:
        return values[block_id]["value"]["value"].strip()

    requester = body["user"]["username"]
    justification = field("justification")

    policy = {
        "name": field("name"),
        "srcintf": _split(field("srcintf")),
        "dstintf": _split(field("dstintf")),
        "srcaddr": _split(field("srcaddr")),
        "dstaddr": _split(field("dstaddr")),
        "service": _split(field("service")),
        "action": "accept",
        "schedule": "always",
        "logtraffic": "all",
        "status": "enable",
        "comment": f"Requested by {requester} ({justification})",
    }

    channel = os.getenv("SLACK_NOTIFY_CHANNEL", body["user"]["id"])
    try:
        pr_url = open_policy_pr(policy, requester, justification)
        client.chat_postMessage(
            channel=channel,
            text=(
                f":memo: <@{body['user']['id']}> requested firewall policy "
                f"*{policy['name']}*. Review & approve: {pr_url}"
            ),
        )
    except Exception as exc:  # surface failures back to the requester
        client.chat_postMessage(
            channel=body["user"]["id"],
            text=f":x: Could not open PR: `{exc}`",
        )


@api.post("/slack/events")
async def slack_events(req: Request):
    return await handler.handle(req)


@api.get("/healthz")
def healthz():
    return {"status": "ok"}
