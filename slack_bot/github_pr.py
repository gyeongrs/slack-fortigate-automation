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

API = "https://api.github.com"
POLICY_PATH = "policies/firewall_policies.yaml"
ADDRESS_PATH = "policies/addresses.yaml"


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
) -> dict:
    """Append one or more per-firewall `policies` to firewall_policies.yaml on a
    new branch and open a PR.

    A request whose traffic transits several firewalls produces one policy per
    firewall (each with that device's interfaces). Any `new_addresses`
    (auto-created from IP/CIDR inputs that matched no existing object) are
    committed to addresses.yaml on the same branch first, so referential
    integrity holds.

    Returns {"url": <html_url>, "number": <pr_number>}.
    """
    cfg = GitHubConfig()
    branch = f"fw-request/{_slug(base_name)}-{int(time.time())}"
    new_addresses = new_addresses or []

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
            client, cfg, branch, base_name, policies, requester,
            justification, new_addresses,
        )


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
) -> dict:
    new_addresses = new_addresses or []
    addr_section = ""
    if new_addresses:
        addr_section = (
            "**Auto-created address objects:**\n```yaml\n"
            + yaml.safe_dump(
                {"addresses": new_addresses}, sort_keys=False, allow_unicode=True
            )
            + "```\n\n"
        )
    devices = ", ".join(p.get("device") or "?" for p in policies)
    body = (
        f"**Requester:** {requester}\n"
        f"**Justification:** {justification}\n"
        f"**Target firewalls (route-selected):** {devices}\n\n"
        + addr_section
        + "**Per-firewall policies:**\n```yaml\n"
        + yaml.safe_dump(
            {"policies": policies}, sort_keys=False, allow_unicode=True
        )
        + "```\n\n"
        "_CI will validate guardrails and show a plan. Merge to apply._"
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
