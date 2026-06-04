"""Slack entrypoint: `/fw-request` opens a modal; submission opens a PR and
posts an approval message with Approve / Reject buttons (mobile-friendly).

Approval rules:
    - Requester != approver (you cannot approve your own request).
    - Approve  -> merge the PR (triggers the apply workflow).
    - Reject   -> close the PR.

Run modes:
    Socket Mode (no public URL needed; best for internal networks):
        set SLACK_APP_TOKEN=xapp-... then:  python -m slack_bot.app
    HTTP mode (request URL):
        uvicorn slack_bot.app:api --port 3000

Slack app config:
    - Slash command  /fw-request
    - Interactivity enabled (Socket Mode toggle, or request URL /slack/events)
    Scopes: commands, chat:write
"""

from __future__ import annotations

import json
import os

from fastapi import FastAPI, Request
from slack_bolt import App
from slack_bolt.adapter.fastapi import SlackRequestHandler

from .github_pr import close_pr, merge_pr, open_policy_pr

app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
)
handler = SlackRequestHandler(app)
api = FastAPI()


# --- modal --------------------------------------------------------------
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


def _approval_blocks(policy_name: str, requester_id: str, pr: dict) -> list[dict]:
    """Message with Approve / Reject buttons. The button `value` carries the
    context needed by the action handlers (PR number + requester)."""
    payload = json.dumps(
        {"pr": pr["number"], "requester": requester_id, "name": policy_name}
    )
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f":memo: <@{requester_id}> requested firewall policy "
                    f"*{policy_name}*.\nReview: {pr['url']}\n"
                    "_Another team member must approve (not the requester)._"
                ),
            },
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
                    "value": payload,
                    "confirm": {
                        "title": {"type": "plain_text", "text": "Approve?"},
                        "text": {
                            "type": "plain_text",
                            "text": f"Merge PR #{pr['number']} and apply "
                            f"'{policy_name}' to the firewall?",
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
                    "value": payload,
                },
            ],
        },
    ]


# --- slash command + submission ----------------------------------------
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

    requester_id = body["user"]["id"]
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

    channel = os.getenv("SLACK_NOTIFY_CHANNEL", requester_id)
    try:
        pr = open_policy_pr(policy, requester, justification)
        client.chat_postMessage(
            channel=channel,
            text=f"Firewall request: {policy['name']} (PR #{pr['number']})",
            blocks=_approval_blocks(policy["name"], requester_id, pr),
        )
    except Exception as exc:  # surface failures back to the requester
        client.chat_postMessage(
            channel=requester_id,
            text=f":x: Could not open PR: `{exc}`",
        )


# --- approval / rejection actions --------------------------------------
def _disable_buttons(client, body, final_text: str) -> None:
    """Replace the original message so the buttons can't be pressed twice."""
    client.chat_update(
        channel=body["channel"]["id"],
        ts=body["message"]["ts"],
        text=final_text,
        blocks=[
            {"type": "section", "text": {"type": "mrkdwn", "text": final_text}}
        ],
    )


@app.action("approve_request")
def handle_approve(ack, body, client):
    ack()
    ctx = json.loads(body["actions"][0]["value"])
    approver_id = body["user"]["id"]

    if approver_id == ctx["requester"]:
        client.chat_postEphemeral(
            channel=body["channel"]["id"],
            user=approver_id,
            text=":no_entry: You cannot approve your own request.",
        )
        return

    try:
        merge_pr(ctx["pr"], body["user"]["username"])
        _disable_buttons(
            client,
            body,
            f":white_check_mark: *{ctx['name']}* approved by <@{approver_id}> "
            f"(PR #{ctx['pr']} merged — applying).",
        )
    except Exception as exc:
        client.chat_postEphemeral(
            channel=body["channel"]["id"],
            user=approver_id,
            text=f":x: Merge failed: `{exc}`",
        )


@app.action("reject_request")
def handle_reject(ack, body, client):
    ack()
    ctx = json.loads(body["actions"][0]["value"])
    approver_id = body["user"]["id"]
    try:
        close_pr(ctx["pr"])
        _disable_buttons(
            client,
            body,
            f":x: *{ctx['name']}* rejected by <@{approver_id}> "
            f"(PR #{ctx['pr']} closed).",
        )
    except Exception as exc:
        client.chat_postEphemeral(
            channel=body["channel"]["id"],
            user=approver_id,
            text=f":x: Could not close PR: `{exc}`",
        )


# --- HTTP mode ----------------------------------------------------------
@api.post("/slack/events")
async def slack_events(req: Request):
    return await handler.handle(req)


@api.get("/healthz")
def healthz():
    return {"status": "ok"}


# --- Socket Mode runner -------------------------------------------------
def run_socket_mode() -> None:
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    app_token = os.environ["SLACK_APP_TOKEN"]  # xapp-...
    SocketModeHandler(app, app_token).start()


if __name__ == "__main__":
    run_socket_mode()
