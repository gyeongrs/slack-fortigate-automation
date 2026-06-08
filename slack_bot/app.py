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
import logging
import os
import traceback

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from slack_bolt import App
from slack_bolt.adapter.fastapi import SlackRequestHandler

from fwgitops.models import Address, DesiredState, Policy, Service
from fwgitops.route_selector import (
    DeviceMatch,
    devices_from_dict,
    load_devices,
    select_targets,
)
from fwgitops.validator import validate as run_validate

from .github_pr import close_pr, fetch_repo_yaml, merge_pr, open_policy_pr

load_dotenv(override=True)  # .env wins over any stale shell/system env vars
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("fw-bot")

_bot_token = os.environ.get("SLACK_BOT_TOKEN")
if not _bot_token:
    raise SystemExit(
        "SLACK_BOT_TOKEN is not set. Copy .env.example to .env and fill in "
        "SLACK_BOT_TOKEN (xoxb-...), SLACK_APP_TOKEN (xapp-...), and "
        "SLACK_SIGNING_SECRET before running the bot."
    )

app = App(
    token=_bot_token,
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
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            ":satellite: The target firewall and interfaces are "
                            "auto-detected from routing — just pick addresses & service."
                        ),
                    }
                ],
            },
            text_input("name", "Policy name", "allow-corp-to-app"),
            text_input("srcaddr", "Source address object(s)", "corp-clients"),
            text_input("dstaddr", "Dest address object(s)", "app-web-server"),
            text_input("service", "Service(s)", "HTTPS, app-https-8443"),
            text_input("justification", "Justification / ticket", "NETOPS-1001"),
        ],
    }


def _approval_blocks(
    policy_name: str, requester_id: str, pr: dict, target_desc: str = ""
) -> list[dict]:
    """Message with Approve / Reject buttons. The button `value` carries the
    context needed by the action handlers (PR number + requester)."""
    payload = json.dumps(
        {"pr": pr["number"], "requester": requester_id, "name": policy_name}
    )
    target_line = f"\n{target_desc}" if target_desc else ""
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f":memo: <@{requester_id}> requested firewall policy "
                    f"*{policy_name}*.{target_line}\nReview: {pr['url']}\n"
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


def _allow_self_approve() -> bool:
    return os.getenv("ALLOW_SELF_APPROVE", "false").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.replace(",", " ").split() if v.strip()]


def _select_target(srcaddr: list[str], dstaddr: list[str]) -> DeviceMatch | None:
    """Pick the firewall on the traffic path (and its interfaces) from routing.

    Uses the repo's address book + config/devices.yaml. Falls back to the local
    devices.yaml if it hasn't been pushed to the repo yet.
    """
    addrs = fetch_repo_yaml("policies/addresses.yaml").get("addresses", [])
    addr_index = {a["name"]: Address(**a) for a in addrs}

    devices = devices_from_dict(fetch_repo_yaml("config/devices.yaml"))
    if not devices:
        devices = load_devices()  # local fallback

    probe = Policy(
        name="_probe",
        srcintf=["auto"],
        dstintf=["auto"],
        srcaddr=srcaddr,
        dstaddr=dstaddr,
        service=["ANY"],
    )
    return select_targets(probe, addr_index, devices).chosen


def _validate_request(policy: dict) -> list[str]:
    """Run the same guardrails as CI against the repo's current definitions
    plus the requested policy. Returns a list of violations (empty == ok)."""
    addrs = fetch_repo_yaml("policies/addresses.yaml").get("addresses", [])
    svcs = fetch_repo_yaml("policies/services.yaml").get("services", [])
    rules = fetch_repo_yaml("config/policy_rules.yaml")
    state = DesiredState(
        addresses=[Address(**a) for a in addrs],
        services=[Service(**s) for s in svcs],
        policies=[Policy(**policy)],
    )
    return run_validate(state, rules)


@app.view("fw_request_submit")
def handle_submission(ack, body, view, client):
    ack()
    values = view["state"]["values"]

    def field(block_id: str) -> str:
        return values[block_id]["value"]["value"].strip()

    requester_id = body["user"]["id"]
    requester = body["user"]["username"]
    justification = field("justification")

    name = field("name")
    srcaddr = _split(field("srcaddr"))
    dstaddr = _split(field("dstaddr"))
    service = _split(field("service"))

    channel = os.getenv("SLACK_NOTIFY_CHANNEL", requester_id)

    # Auto-detect the target firewall + interfaces from routing. If no firewall
    # is on the path (unknown address / no route), we can't determine the
    # interfaces, so reject up front with a helpful message.
    try:
        target = _select_target(srcaddr, dstaddr)
    except Exception as exc:
        log.error("route selection failed:\n%s", traceback.format_exc())
        client.chat_postMessage(
            channel=requester_id,
            text=f":x: Could not auto-detect target firewall: `{exc}`",
        )
        return

    if target is None or target.src_route is None or target.dst_route is None:
        client.chat_postMessage(
            channel=requester_id,
            text=(
                f":no_entry: Request *{name}* rejected (no PR created): no "
                "firewall is on the path between the source and destination.\n"
                "_Check that both address objects exist in "
                "`policies/addresses.yaml` and that a device in "
                "`config/devices.yaml` routes between them._"
            ),
        )
        return

    policy = {
        "name": name,
        "srcintf": [target.src_route.interface],
        "dstintf": [target.dst_route.interface],
        "srcaddr": srcaddr,
        "dstaddr": dstaddr,
        "service": service,
        "action": "accept",
        "schedule": "always",
        "logtraffic": "all",
        "status": "enable",
        "comment": (
            f"Requested by {requester} ({justification}) "
            f"[auto-target: {target.device}]"
        ),
    }

    # Validate BEFORE opening a PR, using the same guardrails as CI, so bad
    # requests (e.g. referencing undefined address objects) are rejected up
    # front instead of failing later in the apply workflow.
    try:
        errors = _validate_request(policy)
    except Exception as exc:
        log.error("request validation lookup failed:\n%s", traceback.format_exc())
        errors = []  # fail open to PR; CI will still catch issues
        client.chat_postMessage(
            channel=requester_id,
            text=f":warning: Could not pre-validate (CI will still check): `{exc}`",
        )
    if errors:
        log.info("Rejected request %s: %s", policy["name"], errors)
        bullet = "\n".join(f"• {e}" for e in errors)
        client.chat_postMessage(
            channel=requester_id,
            text=(
                f":no_entry: Request *{policy['name']}* rejected (no PR created):\n"
                f"{bullet}\n\n_Tip: address objects must already exist in "
                "`policies/addresses.yaml`._"
            ),
        )
        return

    try:
        pr = open_policy_pr(policy, requester, justification)
        log.info("Opened PR #%s for policy %s", pr["number"], policy["name"])
    except Exception as exc:  # GitHub failure (repo/token/branch) — tell requester
        log.error("open_policy_pr failed:\n%s", traceback.format_exc())
        client.chat_postMessage(
            channel=requester_id,
            text=f":x: Could not open PR: `{exc}`",
        )
        return

    target_desc = (
        f":satellite: Auto-target: *{target.device}* "
        f"(srcintf `{target.src_route.interface}` -> "
        f"dstintf `{target.dst_route.interface}`)"
    )
    try:
        client.chat_postMessage(
            channel=channel,
            text=f"Firewall request: {policy['name']} (PR #{pr['number']})",
            blocks=_approval_blocks(policy["name"], requester_id, pr, target_desc),
        )
    except Exception as exc:  # Slack post failure (e.g. not_in_channel)
        log.error("chat_postMessage to %s failed:\n%s", channel, traceback.format_exc())
        client.chat_postMessage(
            channel=requester_id,
            text=(
                f":warning: PR #{pr['number']} was created, but I couldn't post "
                f"to `{channel}`: `{exc}`. Is the bot invited to that channel?"
            ),
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

    # By default the requester cannot approve their own request. Set
    # ALLOW_SELF_APPROVE=true (testing / single-operator setups) to permit it.
    if approver_id == ctx["requester"] and not _allow_self_approve():
        client.chat_postEphemeral(
            channel=body["channel"]["id"],
            user=approver_id,
            text=(
                ":no_entry: You cannot approve your own request. "
                "(Set ALLOW_SELF_APPROVE=true to allow self-approval.)"
            ),
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
