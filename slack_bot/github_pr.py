"""Create a GitHub PR that appends a requested policy to the desired state.

The PR is the audit record and the approval gate: a human reviews and merges,
then CI applies the change. The Slack bot never touches the firewall directly.
"""

from __future__ import annotations

import base64
import os
import time

import httpx
import yaml

from .metadata import decode_meta, encode_meta

API = "https://api.github.com"
POLICY_PATH = "policies/firewall_policies.yaml"
ADDRESS_PATH = "policies/addresses.yaml"
SERVICE_PATH = "policies/services.yaml"


class GitHubConfig:
    def __init__(self) -> None:
        self.token = os.environ["GITHUB_TOKEN"]
        self.repo = os.environ["GITHUB_REPO"]  # "org/name"
        self.base = os.getenv("GITHUB_BASE_BRANCH", "main")

    @property
    def headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }


def _slug(text: str) -> str:
    keep = [c if c.isalnum() else "-" for c in text.lower()]
    return "".join(keep).strip("-")[:40] or "request"


def fetch_repo_yaml(path: str) -> dict:
    """Read and parse a YAML file from the base branch of the repo."""
    cfg = GitHubConfig()
    with httpx.Client(headers=cfg.headers, timeout=30) as client:
        _, content = _get_file(client, cfg, path, cfg.base)
    return yaml.safe_load(content) or {}


def open_policy_pr(
    policies: list[dict],
    base_name: str,
    requester: str,
    justification: str,
    new_addresses: list[dict] | None = None,
    new_services: list[dict] | None = None,
    requester_slack_id: str | None = None,
) -> dict:
    """Append policies (and any new address/service objects) on a new branch.

    Auto-created address objects (IP/CIDR, FQDN, ``name=ip``) land in
    ``addresses.yaml``; auto-created custom services land in ``services.yaml``,
    then policies are appended so referential integrity holds.

    Returns {"url": <html_url>, "number": <pr_number>}.
    """
    cfg = GitHubConfig()
    branch = f"fw-request/{_slug(base_name)}-{int(time.time())}"
    new_addresses = new_addresses or []
    new_services = new_services or []

    with httpx.Client(headers=cfg.headers, timeout=30) as client:
        base_sha = _branch_sha(client, cfg, cfg.base)
        _create_branch(client, cfg, branch, base_sha)

        if new_addresses:
            addr_sha, addr_content = _get_file(client, cfg, ADDRESS_PATH, cfg.base)
            updated_addrs = _append_addresses(addr_content, new_addresses)
            names = ", ".join(a["name"] for a in new_addresses)
            _commit_file(
                client,
                cfg,
                branch,
                ADDRESS_PATH,
                updated_addrs,
                addr_sha,
                message=f"fw-request: add address {names} (by {requester})",
            )

        if new_services:
            svc_sha, svc_content = _get_file(client, cfg, SERVICE_PATH, cfg.base)
            updated_svcs = _append_services(svc_content, new_services)
            names = ", ".join(s["name"] for s in new_services)
            _commit_file(
                client,
                cfg,
                branch,
                SERVICE_PATH,
                updated_svcs,
                svc_sha,
                message=f"fw-request: add service {names} (by {requester})",
            )

        file_sha, content = _get_file(client, cfg, POLICY_PATH, cfg.base)
        updated = _append_policies(content, policies)
        devices = ", ".join(p.get("device") or "?" for p in policies)
        _commit_file(
            client,
            cfg,
            branch,
            POLICY_PATH,
            updated,
            file_sha,
            message=f"fw-request: {base_name} on {devices} (by {requester})",
        )
        return _create_pr(
            client,
            cfg,
            branch,
            base_name,
            policies,
            requester,
            justification,
            new_addresses,
            new_services,
            requester_slack_id,
        )


def open_address_pr(
    new_addresses: list[dict],
    base_name: str,
    requester: str,
    justification: str,
    requester_slack_id: str | None = None,
) -> dict:
    """Append address objects on a new branch and open a PR."""
    cfg = GitHubConfig()
    branch = f"fw-address/{_slug(base_name)}-{int(time.time())}"

    with httpx.Client(headers=cfg.headers, timeout=30) as client:
        base_sha = _branch_sha(client, cfg, cfg.base)
        _create_branch(client, cfg, branch, base_sha)

        addr_sha, addr_content = _get_file(client, cfg, ADDRESS_PATH, cfg.base)
        updated_addrs = _append_addresses(addr_content, new_addresses)
        names = ", ".join(a["name"] for a in new_addresses)
        _commit_file(
            client,
            cfg,
            branch,
            ADDRESS_PATH,
            updated_addrs,
            addr_sha,
            message=f"fw-address: add {names} (by {requester})",
        )
        return _create_address_pr(
            client,
            cfg,
            branch,
            base_name,
            new_addresses,
            requester,
            justification,
            requester_slack_id,
        )


def patch_pr_approver(
    number: int, approver: str, approver_slack_id: str | None = None
) -> None:
    """Record approver in PR metadata before merge (for apply notifications)."""
    cfg = GitHubConfig()
    with httpx.Client(headers=cfg.headers, timeout=30) as client:
        r = client.get(f"{API}/repos/{cfg.repo}/pulls/{number}")
        r.raise_for_status()
        body = r.json().get("body") or ""
        meta = decode_meta(body)
        meta["approver"] = approver
        if approver_slack_id:
            meta["approver_slack_id"] = approver_slack_id
        new_body = _replace_meta(body, meta)
        client.patch(
            f"{API}/repos/{cfg.repo}/pulls/{number}",
            json={"body": new_body},
        ).raise_for_status()


def _replace_meta(body: str, meta: dict) -> str:
    block = encode_meta(meta)
    start = body.find("<!-- fwgitops-meta:")
    if start == -1:
        return body.rstrip() + "\n\n" + block + "\n"
    end = body.find("-->", start)
    if end == -1:
        return body.rstrip() + "\n\n" + block + "\n"
    return body[:start] + block + body[end + 3 :]


def merge_pr(number: int, approver: str) -> str:
    """Merge an approved PR (which triggers the apply workflow). Returns sha."""
    cfg = GitHubConfig()
    with httpx.Client(headers=cfg.headers, timeout=30) as client:
        r = client.put(
            f"{API}/repos/{cfg.repo}/pulls/{number}/merge",
            json={
                "merge_method": "squash",
                "commit_message": f"Approved by {approver} via Slack.",
            },
        )
        r.raise_for_status()
        return r.json().get("sha", "")


def close_pr(number: int) -> None:
    """Close a rejected PR without merging."""
    cfg = GitHubConfig()
    with httpx.Client(headers=cfg.headers, timeout=30) as client:
        r = client.patch(
            f"{API}/repos/{cfg.repo}/pulls/{number}",
            json={"state": "closed"},
        )
        r.raise_for_status()


def _branch_sha(client: httpx.Client, cfg: GitHubConfig, branch: str) -> str:
    r = client.get(f"{API}/repos/{cfg.repo}/git/ref/heads/{branch}")
    r.raise_for_status()
    return r.json()["object"]["sha"]


def _create_branch(
    client: httpx.Client, cfg: GitHubConfig, branch: str, sha: str
) -> None:
    r = client.post(
        f"{API}/repos/{cfg.repo}/git/refs",
        json={"ref": f"refs/heads/{branch}", "sha": sha},
    )
    r.raise_for_status()


def _get_file(
    client: httpx.Client, cfg: GitHubConfig, path: str, ref: str
) -> tuple[str, str]:
    r = client.get(
        f"{API}/repos/{cfg.repo}/contents/{path}", params={"ref": ref}
    )
    r.raise_for_status()
    data = r.json()
    content = base64.b64decode(data["content"]).decode("utf-8")
    return data["sha"], content


def _append_policies(content: str, new_policies: list[dict]) -> str:
    doc = yaml.safe_load(content) or {}
    policies = doc.get("policies") or []
    policies.extend(new_policies)
    doc["policies"] = policies
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)


def _append_addresses(content: str, new_addrs: list[dict]) -> str:
    doc = yaml.safe_load(content) or {}
    addresses = doc.get("addresses") or []
    existing = {a.get("name") for a in addresses}
    for a in new_addrs:
        if a["name"] not in existing:
            addresses.append(a)
            existing.add(a["name"])
    doc["addresses"] = addresses
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)


def _append_services(content: str, new_svcs: list[dict]) -> str:
    doc = yaml.safe_load(content) or {}
    services = doc.get("services") or []
    existing = {s.get("name") for s in services}
    for s in new_svcs:
        if s["name"] not in existing:
            services.append(s)
            existing.add(s["name"])
    doc["services"] = services
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)


def _commit_file(
    client: httpx.Client,
    cfg: GitHubConfig,
    branch: str,
    path: str,
    content: str,
    sha: str,
    message: str,
) -> None:
    r = client.put(
        f"{API}/repos/{cfg.repo}/contents/{path}",
        json={
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "sha": sha,
            "branch": branch,
        },
    )
    r.raise_for_status()


def _create_pr(
    client: httpx.Client,
    cfg: GitHubConfig,
    branch: str,
    base_name: str,
    policies: list[dict],
    requester: str,
    justification: str,
    new_addresses: list[dict] | None = None,
    new_services: list[dict] | None = None,
    requester_slack_id: str | None = None,
) -> dict:
    new_addresses = new_addresses or []
    new_services = new_services or []
    meta = encode_meta(
        {
            "requester": requester,
            "requester_slack_id": requester_slack_id or "",
            "justification": justification,
            "policy_name": base_name,
            "policies": policies,
        }
    )
    addr_section = ""
    if new_addresses:
        addr_section = (
            "**Auto-created address objects:**\n```yaml\n"
            + yaml.safe_dump(
                {"addresses": new_addresses}, sort_keys=False, allow_unicode=True
            )
            + "```\n\n"
        )
    svc_section = ""
    if new_services:
        svc_section = (
            "**Auto-created custom services:**\n```yaml\n"
            + yaml.safe_dump(
                {"services": new_services}, sort_keys=False, allow_unicode=True
            )
            + "```\n\n"
        )
    devices = ", ".join(p.get("device") or "?" for p in policies)
    exp_dates = {p.get("expires_at") for p in policies if p.get("expires_at")}
    expiry_line = ""
    if len(exp_dates) == 1:
        expiry_line = f"**Policy expiry:** {exp_dates.pop()}\n\n"
    body = (
        f"**Requester:** {requester}\n"
        f"**Justification:** {justification}\n"
        f"**Target firewalls (route-selected):** {devices}\n\n"
        + expiry_line
        + addr_section
        + svc_section
        + "**Per-firewall policies:**\n```yaml\n"
        + yaml.safe_dump(
            {"policies": policies}, sort_keys=False, allow_unicode=True
        )
        + "```\n\n"
        "_CI will validate guardrails and show a plan. "
        "`@gyeongrs/netops` CODEOWNERS review is required on GitHub before merge. "
        "After CI passes, use Slack *Approve & merge*._\n\n"
        + meta
    )
    r = client.post(
        f"{API}/repos/{cfg.repo}/pulls",
        json={
            "title": f"fw-request: {base_name} ({devices})",
            "head": branch,
            "base": cfg.base,
            "body": body,
        },
    )
    r.raise_for_status()
    data = r.json()
    return {"url": data["html_url"], "number": data["number"]}


def _create_address_pr(
    client: httpx.Client,
    cfg: GitHubConfig,
    branch: str,
    base_name: str,
    new_addresses: list[dict],
    requester: str,
    justification: str,
    requester_slack_id: str | None = None,
) -> dict:
    meta = encode_meta(
        {
            "requester": requester,
            "requester_slack_id": requester_slack_id or "",
            "justification": justification,
            "policy_name": base_name,
            "request_type": "address",
            "addresses": new_addresses,
        }
    )
    body = (
        f"**Requester:** {requester}\n"
        f"**Justification:** {justification}\n\n"
        "**New address objects:**\n```yaml\n"
        + yaml.safe_dump(
            {"addresses": new_addresses}, sort_keys=False, allow_unicode=True
        )
        + "```\n\n"
        "_CI will validate guardrails. "
        "`@gyeongrs/netops` CODEOWNERS review is required on GitHub before merge._\n\n"
        + meta
    )
    r = client.post(
        f"{API}/repos/{cfg.repo}/pulls",
        json={
            "title": f"fw-address: {base_name}",
            "head": branch,
            "base": cfg.base,
            "body": body,
        },
    )
    r.raise_for_status()
    data = r.json()
    return {"url": data["html_url"], "number": data["number"]}
