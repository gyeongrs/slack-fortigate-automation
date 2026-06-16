"""Fetch PR audit trail from GitHub for Slack apply notifications."""

from __future__ import annotations

import os
import re
from typing import Any

import httpx

from .metadata import decode_meta, extract_policies_yaml, parse_markdown_field

API = "https://api.github.com"


class GitHubConfig:
    def __init__(self) -> None:
        self.token = os.environ["GITHUB_TOKEN"]
        self.repo = os.environ["GITHUB_REPO"]

    @property
    def headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }


def _parse_approver_from_message(message: str) -> str:
    match = re.search(r"Approved by (.+?) via Slack", message)
    return match.group(1).strip() if match else ""


def find_pr_for_commit(client: httpx.Client, cfg: GitHubConfig, sha: str) -> int | None:
    r = client.get(f"{API}/repos/{cfg.repo}/commits/{sha}/pulls", headers=cfg.headers)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    pulls = r.json()
    if not pulls:
        return None
    merged = [p for p in pulls if p.get("merged_at")]
    target = merged[0] if merged else pulls[0]
    return target.get("number")


def fetch_pr_audit(
    pr_number: int | None = None,
    commit_sha: str | None = None,
) -> dict[str, Any]:
    """Build an audit dict for Slack from a PR and/or merge commit."""
    cfg = GitHubConfig()
    audit: dict[str, Any] = {
        "pr_number": pr_number,
        "commit_sha": commit_sha or "",
        "requester": "?",
        "requester_slack_id": "",
        "approver": "?",
        "approver_slack_id": "",
        "justification": "",
        "policy_name": "",
        "pr_url": "",
        "commit_url": "",
        "changed_files": [],
        "commits": [],
        "policies": [],
    }

    with httpx.Client(timeout=30) as client:
        if pr_number is None and commit_sha:
            pr_number = find_pr_for_commit(client, cfg, commit_sha)
            audit["pr_number"] = pr_number

        if commit_sha:
            audit["commit_url"] = f"https://github.com/{cfg.repo}/commit/{commit_sha}"
            cr = client.get(
                f"{API}/repos/{cfg.repo}/commits/{commit_sha}", headers=cfg.headers
            )
            if cr.status_code == 200:
                cdata = cr.json()
                audit["commit_sha"] = cdata.get("sha", commit_sha)
                audit["changed_files"] = [
                    f["filename"] for f in cdata.get("files", [])
                ]
                msg = cdata.get("commit", {}).get("message", "")
                approver = _parse_approver_from_message(msg)
                if approver:
                    audit["approver"] = approver

        if pr_number is None:
            return audit

        audit["pr_url"] = f"https://github.com/{cfg.repo}/pull/{pr_number}"
        pr = client.get(
            f"{API}/repos/{cfg.repo}/pulls/{pr_number}", headers=cfg.headers
        )
        pr.raise_for_status()
        pdata = pr.json()
        body = pdata.get("body") or ""
        meta = decode_meta(body)

        audit["requester"] = meta.get("requester") or parse_markdown_field(
            body, "Requester"
        )
        audit["requester_slack_id"] = meta.get("requester_slack_id") or ""
        audit["approver_slack_id"] = meta.get("approver_slack_id") or ""
        audit["justification"] = meta.get("justification") or parse_markdown_field(
            body, "Justification"
        )
        audit["policy_name"] = meta.get("policy_name") or pdata.get("title", "")
        audit["policies"] = meta.get("policies") or extract_policies_yaml(body)

        if meta.get("approver"):
            audit["approver"] = meta["approver"]
        elif audit["approver"] == "?":
            merged_by = pdata.get("merged_by") or {}
            if merged_by.get("login"):
                audit["approver"] = merged_by["login"]

        commits_r = client.get(
            f"{API}/repos/{cfg.repo}/pulls/{pr_number}/commits",
            headers=cfg.headers,
        )
        if commits_r.status_code == 200:
            audit["commits"] = [
                {
                    "sha": c.get("sha"),
                    "message": (c.get("commit") or {}).get("message", ""),
                }
                for c in commits_r.json()
            ]

    return audit


def parse_apply_log(log_text: str) -> list[str]:
    """Extract notable lines from fwctl apply output."""
    actions: list[str] = []
    for line in log_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(
            tag in stripped
            for tag in ("[created]", "[updated]", "[ERROR]", "applying", "Refusing")
        ):
            actions.append(stripped)
    return actions
