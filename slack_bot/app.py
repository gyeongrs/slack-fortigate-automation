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
    - Slash commands  /fw-request, /fw-address
    - Interactivity enabled (Socket Mode toggle, or request URL /slack/events)
    Scopes: commands, chat:write
"""

from __future__ import annotations

import json
import logging
import os
import traceback
from datetime import date

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from slack_bolt import App
from slack_bolt.adapter.fastapi import SlackRequestHandler

from fwgitops.address_resolver import build_address_object, resolve_addresses
from fwgitops.expiry import expires_at_from_valid_days, load_expiry_config
from fwgitops.models import Address, DesiredState, Policy, Service
from fwgitops.router_monitor import attach_live_clients, load_devices_live
from fwgitops.route_selector import (
    DeviceMatch,
    devices_from_dict,
    load_devices,
    select_targets,
)
from fwgitops.policy_naming import (
    build_policy_name,
    load_naming_config,
    request_summary_name,
)
from fwgitops.service_resolver import resolve_services
from fwgitops.validator import validate as run_validate

from .github_pr import (
    close_pr,
    fetch_repo_yaml,
    merge_pr,
    open_address_pr,
    open_policy_pr,
    patch_pr_approver,
)
from .messages import address_summary_blocks, request_summary_blocks
from .metadata import logtraffic_summary

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
                            ":satellite: Target firewall & interfaces are "
                            "auto-detected from routing. Addresses: existing "
                            "object name, or new object spec "
                            "`name=10.51.10.1 prefix=32 zone=ch expire=90 "
                            "comment=NETOPS`. Services: built-in (HTTPS), "
                            "catalog name, `8443`, `tcp/9000`, or "
                            "`svc=tcp/8443`. Use `/fw-address` to register "
                            "addresses first. Policy name: "
                            "{center}{zone}{src}>{center}{zone}{dst}."
                        ),
                    }
                ],
            },
            text_input(
                "srcaddr", "Source (object name or IP/CIDR)", "corp-clients or 10.20.0.0/16"
            ),
            text_input(
                "dstaddr", "Destination (object name or IP/CIDR)", "app-web-server or 10.99.5.10/32"
            ),
            text_input("service", "Service(s)", "HTTPS, 8443, tcp/9000, app-https-8443"),
            text_input("valid_days", "Expire Day", "90"),
            text_input("justification", "Comments", "NETOPS-1001"),
        ],
    }


def _address_modal() -> dict:
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
        "callback_id": "fw_address_submit",
        "title": {"type": "plain_text", "text": "Address Request"},
        "submit": {"type": "plain_text", "text": "Open PR"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            "Adds an address object to `addresses.yaml`. "
                            "`zone` must match `policy_rules.yaml` "
                            "(core, ch, svr, vdi, dmz, inet, mgt, exco, cc)."
                        ),
                    }
                ],
            },
            text_input("name", "name", "ch-app-01"),
            text_input("address", "address", "10.51.10.15"),
            text_input("prefix", "Prefix", "32"),
            text_input("valid_days", "Expire Day", "90"),
            text_input("justification", "Comments", "NETOPS-1001"),
            text_input("zone", "Zone", "ch"),
        ],
    }


# --- slash command + submission ----------------------------------------
@app.command("/fw-request")
def open_request_modal(ack, body, client):
    ack()
    client.views_open(trigger_id=body["trigger_id"], view=_modal())


@app.command("/fw-address")
def open_address_modal(ack, body, client):
    ack()
    client.views_open(trigger_id=body["trigger_id"], view=_address_modal())


def _allow_self_approve() -> bool:
    return os.getenv("ALLOW_SELF_APPROVE", "false").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.replace(",", " ").split() if v.strip()]


def _parse_valid_days(raw: str, rules: dict) -> tuple[date | None, list[str]]:
    """Return (expires_at, errors). Empty input uses default_valid_days."""
    cfg = load_expiry_config(rules)
    text = raw.strip()
    if not text:
        days = cfg.default_valid_days
    else:
        try:
            days = int(text.split()[0])
        except ValueError:
            return None, ["Expire Day must be a number of days (e.g. 90)."]
    if days <= 0:
        return None, ["Expire Day must be at least 1 day."]
    if days > cfg.max_valid_days:
        return None, [
            f"Expire Day {days} exceeds max_valid_days={cfg.max_valid_days}."
        ]
    return expires_at_from_valid_days(days), []


def _select_targets(
    srcaddr: list[str], dstaddr: list[str], addr_objs: list[dict]
) -> list[DeviceMatch]:
    """Return EVERY firewall the traffic transits (each with its interfaces).

    Traffic between two endpoints can pass through several firewalls in series;
    each one needs its own allow policy, so we return all transit matches (most
    specific first), not just the single best.

    ``addr_objs`` is the merged address book (repo objects + any auto-created
    ones) so freshly proposed IPs are routable. Devices come from the repo's
    config/devices.yaml, falling back to the local file if not yet pushed.
    """
    addr_index = {a["name"]: Address(**a) for a in addr_objs}

    devices = devices_from_dict(fetch_repo_yaml("config/devices.yaml"))
    if not devices:
        devices = load_devices_live()  # local fallback; live lookup when configured
    else:
        devices = attach_live_clients(devices)

    probe = Policy(
        name="_probe",
        srcintf=["auto"],
        dstintf=["auto"],
        srcaddr=srcaddr,
        dstaddr=dstaddr,
        service=["ANY"],
    )
    return select_targets(probe, addr_index, devices).transit


def _validate_request(
    policies: list[dict],
    addr_objs: list[dict],
    svc_objs: list[dict] | None = None,
) -> list[str]:
    """Run the same guardrails as CI against the merged definitions plus the
    requested policies. Returns a list of violations (empty == ok)."""
    svcs = svc_objs if svc_objs is not None else fetch_repo_yaml(
        "policies/services.yaml"
    ).get("services", [])
    rules = fetch_repo_yaml("config/policy_rules.yaml")
    state = DesiredState(
        addresses=[Address(**a) for a in addr_objs],
        services=[Service(**s) for s in svcs],
        policies=[Policy(**p) for p in policies],
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
    requester_real = body["user"].get("name") or requester
    team_name = (body.get("team") or {}).get("domain") or ""
    justification = field("justification")

    name = "pending"  # replaced after route + naming
    srcaddr = _split(field("srcaddr"))
    dstaddr = _split(field("dstaddr"))
    service = _split(field("service"))
    valid_days_raw = field("valid_days")

    try:
        rules = fetch_repo_yaml("config/policy_rules.yaml")
    except Exception:
        rules = {}

    expires_at, valid_errors = _parse_valid_days(valid_days_raw, rules)
    if valid_errors:
        client.chat_postMessage(
            channel=requester_id,
            text=(
                f":no_entry: Request *{name}* rejected (no PR created):\n"
                + "\n".join(f"• {e}" for e in valid_errors)
            ),
        )
        return

    channel = os.getenv("SLACK_NOTIFY_CHANNEL", requester_id)

    # Resolve IP / CIDR inputs (e.g. 10.99.5.10/32) to existing address object
    # names by matching the address book. Object names pass through unchanged.
    try:
        addr_objs = fetch_repo_yaml("policies/addresses.yaml").get("addresses", [])
    except Exception as exc:
        log.error("address book lookup failed:\n%s", traceback.format_exc())
        client.chat_postMessage(
            channel=requester_id,
            text=f":x: Could not read the address book: `{exc}`",
        )
        return

    autocomment = f"Auto-created from Slack request by {requester}"
    src_names, src_new, src_bad = resolve_addresses(
        srcaddr, addr_objs, autocomment, autocreate=True, rules=rules
    )
    dst_names, dst_new, dst_bad = resolve_addresses(
        dstaddr, addr_objs + src_new, autocomment, autocreate=True, rules=rules
    )
    if src_bad or dst_bad:
        client.chat_postMessage(
            channel=requester_id,
            text=(
                f":no_entry: Request *{name}* rejected (no PR created):\n"
                + "\n".join(f"• {b}" for b in (src_bad + dst_bad))
                + "\n_Use `/fw-address` or "
                "`name=IP prefix=32 zone=ch expire=90` for new objects._"
            ),
        )
        return
    srcaddr, dstaddr = src_names, dst_names
    new_addresses = src_new + dst_new
    merged_addr_objs = addr_objs + new_addresses

    try:
        svc_objs = fetch_repo_yaml("policies/services.yaml").get("services", [])
        builtin = set(
            (rules or fetch_repo_yaml("config/policy_rules.yaml")).get(
                "allowed_builtin_services", []
            )
        )
    except Exception as exc:
        log.error("service catalog lookup failed:\n%s", traceback.format_exc())
        client.chat_postMessage(
            channel=requester_id,
            text=f":x: Could not read services.yaml: `{exc}`",
        )
        return

    svc_names, svc_new, svc_bad = resolve_services(
        service, svc_objs, builtin, autocomment, autocreate=True
    )
    if svc_bad:
        bad = ", ".join(f"`{b}`" for b in svc_bad)
        client.chat_postMessage(
            channel=requester_id,
            text=(
                f":no_entry: Request *{name}* rejected (no PR created): "
                f"{bad} is not a known service, built-in, or port "
                f"(e.g. `8443`, `tcp/9000`, `my-svc=tcp/8443`)."
            ),
        )
        return
    service = svc_names
    new_services = svc_new
    merged_svc_objs = svc_objs + new_services

    # Auto-detect EVERY firewall the traffic transits (it may pass through
    # several in series; each needs its own allow policy). If none is on the
    # path, reject up front with a helpful message.
    try:
        targets = _select_targets(srcaddr, dstaddr, merged_addr_objs)
    except Exception as exc:
        log.error("route selection failed:\n%s", traceback.format_exc())
        client.chat_postMessage(
            channel=requester_id,
            text=f":x: Could not auto-detect target firewall(s): `{exc}`",
        )
        return

    if not targets:
        client.chat_postMessage(
            channel=requester_id,
            text=(
                f":no_entry: Request *{name}* rejected (no PR created): no "
                "firewall is on the path between the source and destination.\n"
                "_No device in `config/devices.yaml` routes between these "
                "endpoints (src and dst must transit a firewall)._"
            ),
        )
        return

    naming = load_naming_config(rules)

    # One policy per transit firewall; name = {center}{zone}{src}>{center}{zone}{dst}
    policies = [
        {
            "name": build_policy_name(
                t.device, srcaddr, dstaddr, merged_addr_objs, naming
            ),
            "device": t.device,
            "srcintf": [t.src_route.interface],
            "dstintf": [t.dst_route.interface],
            "srcaddr": srcaddr,
            "dstaddr": dstaddr,
            "service": service,
            "action": "accept",
            "schedule": "always",
            "logtraffic": "all",
            "status": "enable",
            "expires_at": expires_at.isoformat(),
            "requester": requester,
            "requester_slack_id": requester_id,
            "comment": f"Requested by {requester} ({justification}) [{t.device}]",
        }
        for t in targets
    ]
    name = request_summary_name(srcaddr, dstaddr, merged_addr_objs)

    # Validate BEFORE opening a PR
    # requests (e.g. referencing undefined address objects) are rejected up
    # front instead of failing later in the apply workflow.
    try:
        errors = _validate_request(policies, merged_addr_objs, merged_svc_objs)
    except Exception as exc:
        log.error("request validation lookup failed:\n%s", traceback.format_exc())
        errors = []  # fail open to PR; CI will still catch issues
        client.chat_postMessage(
            channel=requester_id,
            text=f":warning: Could not pre-validate (CI will still check): `{exc}`",
        )
    if errors:
        log.info("Rejected request %s: %s", name, errors)
        bullet = "\n".join(f"• {e}" for e in errors)
        client.chat_postMessage(
            channel=requester_id,
            text=(
                f":no_entry: Request *{name}* rejected (no PR created):\n"
                f"{bullet}"
            ),
        )
        return

    try:
        pr = open_policy_pr(
            policies,
            name,
            requester,
            justification,
            new_addresses,
            new_services,
            requester_slack_id=requester_id,
        )
        log.info("Opened PR #%s for %s (%d firewall(s))", pr["number"], name, len(policies))
    except Exception as exc:  # GitHub failure (repo/token/branch) — tell requester
        log.error("open_policy_pr failed:\n%s", traceback.format_exc())
        client.chat_postMessage(
            channel=requester_id,
            text=f":x: Could not open PR: `{exc}`",
        )
        return

    target_fw = [
        {
            "device": t.device,
            "srcintf": t.src_route.interface,  # type: ignore[union-attr]
            "dstintf": t.dst_route.interface,  # type: ignore[union-attr]
        }
        for t in targets
    ]
    try:
        client.chat_postMessage(
            channel=channel,
            text=f"Firewall request PR #{pr['number']}: {name}",
            blocks=request_summary_blocks(
                policy_name=name,
                requester_id=requester_id,
                requester_name=requester,
                requester_real_name=requester_real,
                team_name=team_name,
                justification=justification,
                pr=pr,
                policies=policies,
                targets=target_fw,
                new_addresses=new_addresses,
                new_services=new_services,
                expires_at=expires_at.isoformat() if expires_at else None,
            ),
        )
        client.chat_postMessage(
            channel=requester_id,
            text=(
                f":inbox_tray: Request *{name}* logged as PR #{pr['number']}.\n"
                f"{logtraffic_summary(policies)}"
            ),
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


@app.view("fw_address_submit")
def handle_address_submission(ack, body, view, client):
    ack()
    values = view["state"]["values"]

    def field(block_id: str) -> str:
        return values[block_id]["value"]["value"].strip()

    requester_id = body["user"]["id"]
    requester = body["user"]["username"]
    requester_real = body["user"].get("name") or requester
    team_name = (body.get("team") or {}).get("domain") or ""
    justification = field("justification")
    obj_name = field("name")
    address = field("address")
    prefix = field("prefix") or "32"
    zone = field("zone")
    valid_days_raw = field("valid_days")

    try:
        rules = fetch_repo_yaml("config/policy_rules.yaml")
    except Exception:
        rules = {}

    expires_at, valid_errors = _parse_valid_days(valid_days_raw, rules)
    if valid_errors:
        client.chat_postMessage(
            channel=requester_id,
            text=(
                ":no_entry: Address request rejected (no PR created):\n"
                + "\n".join(f"• {e}" for e in valid_errors)
            ),
        )
        return

    try:
        addr_objs = fetch_repo_yaml("policies/addresses.yaml").get("addresses", [])
    except Exception as exc:
        client.chat_postMessage(
            channel=requester_id,
            text=f":x: Could not read the address book: `{exc}`",
        )
        return

    taken = {a.get("name") for a in addr_objs if a.get("name")}
    comment = justification or f"Requested by {requester} via /fw-address"
    new_obj, build_errors = build_address_object(
        name=obj_name,
        address=address,
        prefix=prefix,
        zone=zone,
        expires_at=expires_at,
        comment=comment,
        taken=taken,
        rules=rules,
    )
    if build_errors or new_obj is None:
        client.chat_postMessage(
            channel=requester_id,
            text=(
                ":no_entry: Address request rejected (no PR created):\n"
                + "\n".join(f"• {e}" for e in (build_errors or ["unknown error"]))
            ),
        )
        return

    try:
        Address(**new_obj)
    except Exception as exc:
        client.chat_postMessage(
            channel=requester_id,
            text=f":no_entry: Invalid address object: `{exc}`",
        )
        return

    summary_name = new_obj["name"]
    channel = os.getenv("SLACK_NOTIFY_CHANNEL", requester_id)

    try:
        pr = open_address_pr(
            [new_obj],
            summary_name,
            requester,
            justification,
            requester_slack_id=requester_id,
        )
        log.info("Opened address PR #%s for %s", pr["number"], summary_name)
    except Exception as exc:
        log.error("open_address_pr failed:\n%s", traceback.format_exc())
        client.chat_postMessage(
            channel=requester_id,
            text=f":x: Could not open PR: `{exc}`",
        )
        return

    try:
        client.chat_postMessage(
            channel=channel,
            text=f"Address request PR #{pr['number']}: {summary_name}",
            blocks=address_summary_blocks(
                summary_name=summary_name,
                requester_id=requester_id,
                requester_name=requester,
                requester_real_name=requester_real,
                team_name=team_name,
                justification=justification,
                pr=pr,
                new_addresses=[new_obj],
            ),
        )
        client.chat_postMessage(
            channel=requester_id,
            text=(
                f":inbox_tray: Address *{summary_name}* logged as PR #{pr['number']}."
            ),
        )
    except Exception as exc:
        log.error("chat_postMessage failed:\n%s", traceback.format_exc())
        client.chat_postMessage(
            channel=requester_id,
            text=(
                f":warning: PR #{pr['number']} was created, but posting to "
                f"`{channel}` failed: `{exc}`"
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
        patch_pr_approver(
            ctx["pr"],
            body["user"]["username"],
            approver_slack_id=approver_id,
        )
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
