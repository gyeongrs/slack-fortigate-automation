"""Slack entrypoint: `/fw-policy` opens a modal; submission opens a PR and
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
    - Slash commands  /fw-policy, /fw-address
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

from fwgitops.address_resolver import (
    build_address_object,
    classify_address_tokens,
    suggest_address_defaults,
)
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

_METADATA_MAX = 3000


def _pack_pending(pending: dict) -> str:
    raw = json.dumps(pending, separators=(",", ":"), ensure_ascii=False)
    if len(raw) > _METADATA_MAX:
        raise ValueError(
            f"Policy wizard state too large ({len(raw)} chars); "
            "reduce the number of new addresses per request."
        )
    return raw


def _unpack_pending(raw: str) -> dict | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


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
        "callback_id": "fw_policy_submit",
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
                            "auto-detected from routing. Source/destination: "
                            "existing object name or IP/CIDR/FQDN — if the "
                            "object does not exist, an address form opens "
                            "automatically (same as `/fw-address`). Services: "
                            "built-in (HTTPS), catalog name, `8443`, "
                            "`tcp/9000`, or `svc=tcp/8443`."
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
@app.command("/fw-policy")
def open_request_modal(ack, body, client):
    ack()
    client.views_open(trigger_id=body["trigger_id"], view=_modal())


@app.command("/fw-address")
def open_address_modal(ack, body, client):
    ack()
    try:
        client.views_open(trigger_id=body["trigger_id"], view=_address_modal())
    except Exception as exc:
        log.error("views_open failed for /fw-address:\n%s", traceback.format_exc())
        client.chat_postEphemeral(
            channel=body["channel_id"],
            user=body["user_id"],
            text=(
                f":x: Could not open Address Request form: `{exc}`\n"
                "If the command itself is unknown, add `/fw-address` under "
                "*Features → Slash Commands* in your Slack app settings."
            ),
        )


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


def _modal_text_input(
    block_id: str,
    label: str,
    placeholder: str,
    *,
    initial: str = "",
) -> dict:
    element: dict = {
        "type": "plain_text_input",
        "action_id": "value",
        "placeholder": {"type": "plain_text", "text": placeholder},
    }
    if initial:
        element["initial_value"] = initial[:3000]
    return {
        "type": "input",
        "block_id": block_id,
        "label": {"type": "plain_text", "text": label},
        "element": element,
    }


def _policy_address_step_modal(
    pending: dict,
    token: str,
    *,
    step: int,
    total: int,
    defaults: dict[str, str],
    valid_days_default: str,
    comments_default: str,
) -> dict:
    return {
        "type": "modal",
        "callback_id": "fw_policy_address_step",
        "private_metadata": _pack_pending(pending),
        "title": {"type": "plain_text", "text": f"Address ({step}/{total})"},
        "submit": {"type": "plain_text", "text": "Next" if step < total else "Create PR"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            f":busts_in_silhouette: Policy needs a new address object "
                            f"for `{token}`. Fill in the fields below "
                            f"(same as `/fw-address`)."
                        ),
                    }
                ],
            },
            _modal_text_input("name", "name", "ch-app-01", initial=defaults.get("name", "")),
            _modal_text_input(
                "address", "address", "10.51.10.15", initial=defaults.get("address", "")
            ),
            _modal_text_input("prefix", "Prefix", "32", initial=defaults.get("prefix", "32")),
            _modal_text_input("valid_days", "Expire Day", "90", initial=valid_days_default),
            _modal_text_input("justification", "Comments", "NETOPS-1001", initial=comments_default),
            _modal_text_input("zone", "Zone", "ch"),
        ],
    }


def _finalize_policy_request(client, pending: dict) -> None:
    """Open policy PR after all address objects are resolved."""
    requester_id = pending["requester_id"]
    requester = pending["requester"]
    requester_real = pending["requester_real"]
    team_name = pending["team_name"]
    justification = pending["justification"]
    srcaddr_raw = pending["srcaddr_raw"]
    dstaddr_raw = pending["dstaddr_raw"]
    service = pending["service"]
    valid_days_raw = pending["valid_days_raw"]
    inline_new = pending.get("inline_new") or []
    wizard_new = pending.get("created") or []
    name = "pending"

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

    try:
        addr_objs = fetch_repo_yaml("policies/addresses.yaml").get("addresses", [])
    except Exception as exc:
        client.chat_postMessage(
            channel=requester_id,
            text=f":x: Could not read the address book: `{exc}`",
        )
        return

    autocomment = f"Auto-created from Slack policy request by {requester}"
    merged_pool = addr_objs + inline_new + wizard_new
    token_map: dict[str, str] = pending.get("token_map") or {}

    def _names_for_side(raw_tokens: list[str]) -> tuple[list[str] | None, list[str]]:
        names: list[str] = []
        pool = list(merged_pool)
        for t in raw_tokens:
            if t in token_map:
                if token_map[t] not in names:
                    names.append(token_map[t])
                continue
            resolved, new_objs, need = classify_address_tokens(
                [t], pool, autocomment, rules=rules
            )
            if need:
                return None, need
            pool.extend(new_objs)
            names.extend(resolved)
        return names, []

    srcaddr, src_bad = _names_for_side(srcaddr_raw)
    if src_bad:
        client.chat_postMessage(
            channel=requester_id,
            text=(
                ":no_entry: Request rejected (no PR created): could not resolve "
                f"source `{src_bad[0]}`. Please run `/fw-policy` again."
            ),
        )
        return
    dstaddr, dst_bad = _names_for_side(dstaddr_raw)
    if dst_bad:
        client.chat_postMessage(
            channel=requester_id,
            text=(
                ":no_entry: Request rejected (no PR created): could not resolve "
                f"destination `{dst_bad[0]}`. Please run `/fw-policy` again."
            ),
        )
        return

    new_addresses = inline_new + wizard_new
    seen_addr_names: set[str] = set()
    deduped_addresses: list[dict] = []
    for a in new_addresses:
        n = a.get("name")
        if n and n not in seen_addr_names:
            deduped_addresses.append(a)
            seen_addr_names.add(n)
    new_addresses = deduped_addresses
    merged_addr_objs = addr_objs + new_addresses

    try:
        svc_objs = fetch_repo_yaml("policies/services.yaml").get("services", [])
        builtin = set((rules or {}).get("allowed_builtin_services", []))
    except Exception as exc:
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
                f"{bad} is not a known service, built-in, or port."
            ),
        )
        return
    service = svc_names
    new_services = svc_new
    merged_svc_objs = svc_objs + new_services

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
                "firewall is on the path between the source and destination."
            ),
        )
        return

    naming = load_naming_config(rules)
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
    name = request_summary_name(srcaddr, dstaddr, merged_addr_objs, naming)

    try:
        errors = _validate_request(policies, merged_addr_objs, merged_svc_objs)
    except Exception as exc:
        log.error("request validation lookup failed:\n%s", traceback.format_exc())
        errors = []
        client.chat_postMessage(
            channel=requester_id,
            text=f":warning: Could not pre-validate (CI will still check): `{exc}`",
        )
    if errors:
        bullet = "\n".join(f"• {e}" for e in errors)
        client.chat_postMessage(
            channel=requester_id,
            text=f":no_entry: Request *{name}* rejected (no PR created):\n{bullet}",
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
    except Exception as exc:
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
    except Exception as exc:
        log.error("chat_postMessage failed:\n%s", traceback.format_exc())
        client.chat_postMessage(
            channel=requester_id,
            text=(
                f":warning: PR #{pr['number']} was created, but posting to "
                f"`{channel}` failed: `{exc}`"
            ),
        )


@app.view("fw_policy_submit")
def handle_submission(ack, body, view, client):
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
        ack()
        client.chat_postMessage(
            channel=requester_id,
            text=(
                f":no_entry: Request *{name}* rejected (no PR created):\n"
                + "\n".join(f"• {e}" for e in valid_errors)
            ),
        )
        return

    try:
        addr_objs = fetch_repo_yaml("policies/addresses.yaml").get("addresses", [])
    except Exception as exc:
        ack()
        client.chat_postMessage(
            channel=requester_id,
            text=f":x: Could not read the address book: `{exc}`",
        )
        return

    autocomment = f"Auto-created from Slack request by {requester}"
    _, src_new, src_need = classify_address_tokens(
        srcaddr, addr_objs, autocomment, rules=rules
    )
    _, dst_new, dst_need = classify_address_tokens(
        dstaddr, addr_objs + src_new, autocomment, rules=rules
    )

    need_form: list[str] = []
    for t in src_need + dst_need:
        if t not in need_form:
            need_form.append(t)

    if need_form:
        pending = {
            "requester_id": requester_id,
            "requester": requester,
            "requester_real": requester_real,
            "team_name": team_name,
            "justification": justification,
            "srcaddr_raw": srcaddr,
            "dstaddr_raw": dstaddr,
            "service": service,
            "valid_days_raw": valid_days_raw,
            "inline_new": src_new + dst_new,
            "queue": need_form,
            "created": [],
            "token_map": {},
            "total_steps": len(need_form),
        }
        token = need_form[0]
        defaults = suggest_address_defaults(token)
        try:
            ack(
                response_action="update",
                view=_policy_address_step_modal(
                    pending,
                    token,
                    step=1,
                    total=len(need_form),
                    defaults=defaults,
                    valid_days_default=valid_days_raw or "90",
                    comments_default=justification,
                ),
            )
        except Exception as exc:
            log.error("address wizard views update failed:\n%s", traceback.format_exc())
            ack()
            client.chat_postMessage(
                channel=requester_id,
                text=(
                    f":x: Could not open address form: `{exc}`\n"
                    "Fill in zone on the next screen, or use `/fw-address` first."
                ),
            )
        return

    ack()
    _finalize_policy_request(
        client,
        {
            "requester_id": requester_id,
            "requester": requester,
            "requester_real": requester_real,
            "team_name": team_name,
            "justification": justification,
            "srcaddr_raw": srcaddr,
            "dstaddr_raw": dstaddr,
            "service": service,
            "valid_days_raw": valid_days_raw,
            "inline_new": src_new + dst_new,
            "created": [],
            "token_map": {},
        },
    )


@app.view("fw_policy_address_step")
def handle_policy_address_step(ack, body, view, client):
    pending = _unpack_pending(view.get("private_metadata") or "")
    if not pending:
        ack()
        client.chat_postMessage(
            channel=body["user"]["id"],
            text=(
                ":x: Could not restore policy wizard state — "
                "please submit `/fw-policy` again."
            ),
        )
        return

    values = view["state"]["values"]

    def field(block_id: str) -> str:
        return values[block_id]["value"]["value"].strip()

    requester_id = body["user"]["id"]
    requester = body["user"]["username"]
    queue = pending.get("queue") or []
    if not queue:
        ack()
        _finalize_policy_request(client, pending)
        return

    token = queue[0]
    obj_name = field("name")
    address = field("address")
    prefix = field("prefix") or "32"
    zone = field("zone")
    valid_days_raw = field("valid_days") or pending.get("valid_days_raw", "90")
    addr_comment = field("justification") or pending.get("justification", "")

    try:
        rules = fetch_repo_yaml("config/policy_rules.yaml")
    except Exception:
        rules = {}

    expires_at, valid_errors = _parse_valid_days(valid_days_raw, rules)
    if valid_errors:
        ack(
            response_action="errors",
            errors={"zone": valid_errors[0][:150]},
        )
        return

    try:
        addr_objs = fetch_repo_yaml("policies/addresses.yaml").get("addresses", [])
    except Exception:
        addr_objs = []

    taken = {a.get("name") for a in addr_objs if a.get("name")}
    for a in (pending.get("inline_new") or []) + (pending.get("created") or []):
        if a.get("name"):
            taken.add(a["name"])

    comment = addr_comment or f"Auto-created for policy by {requester}"
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
        ack(
            response_action="errors",
            errors={"zone": (build_errors or ["invalid address"])[0][:150]},
        )
        return

    try:
        Address(**new_obj)
    except Exception as exc:
        ack(response_action="errors", errors={"name": str(exc)[:150]})
        return

    pending.setdefault("created", []).append(new_obj)
    pending.setdefault("token_map", {})[token] = new_obj["name"]
    queue.pop(0)
    pending["queue"] = queue

    if queue:
        next_token = queue[0]
        step = len(pending.get("created", [])) + 1
        total = pending.get("total_steps", step + len(queue) - 1)
        defaults = suggest_address_defaults(next_token)
        ack(
            response_action="update",
            view=_policy_address_step_modal(
                pending,
                next_token,
                step=step,
                total=total,
                defaults=defaults,
                valid_days_default=pending.get("valid_days_raw", "90"),
                comments_default=pending.get("justification", ""),
            ),
        )
        return

    ack()
    _finalize_policy_request(client, pending)


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
