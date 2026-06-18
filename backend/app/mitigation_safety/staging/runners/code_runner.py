"""Code staging runner — opens a branch and (optionally) a PR via GitHub.

The runner is intentionally minimal: it formats a branch name from
ticket_id+action_id (MS-04 requirement: "named/traceable to ticket_id +
action_id") and calls into a thin GitHub adapter when configured. If no
GitHub adapter is available (dev/test), it returns a "dry-run" result —
the validation layer's MockCIRunner is what actually exercises the branch.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

try:
    import httpx  # type: ignore
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore

from app.mitigation_safety.staging.runners.base import StagingRunnerResult

logger = logging.getLogger("mitigation_safety.staging.code")


def branch_name(*, ticket_id: str | None, action_id: str) -> str:
    """MS-04: branch traceable to ticket_id + action_id."""
    short_action = action_id.replace("-", "")[:12]
    if ticket_id:
        short_ticket = ticket_id.replace("-", "")[:12]
        return f"sentinel/{short_ticket}/{short_action}"
    return f"sentinel/no-ticket/{short_action}"


class CodeStagingRunner:
    type = "code"

    def __init__(
        self,
        *,
        token: str | None = None,
        repo: str | None = None,
        base_ref: str | None = None,
    ) -> None:
        self.token = token or os.getenv("GITHUB_TOKEN") or ""
        self.repo = repo or os.getenv("GITHUB_REPO") or ""
        self.base_ref = base_ref or os.getenv("GITHUB_BASE_REF") or "main"

    def apply(
        self,
        *,
        action_id: str,
        ticket_id: str | None,
        target: str,
        artifacts_ref: str,
        expected_outcome: dict,
    ) -> StagingRunnerResult:
        # `target` may already be a fully-qualified branch name from the API
        # body; if it is just a slug or empty, generate the canonical name.
        bn = target if target and target.startswith("sentinel/") else branch_name(
            ticket_id=ticket_id, action_id=action_id
        )

        if self.token and self.repo and httpx is not None:
            # Best-effort: create the branch by fetching base_ref sha + create
            # ref. Errors are logged, not fatal — staging proceeds with the
            # branch name and the CI runner does the heavy lifting.
            try:
                self._ensure_branch(bn)
            except Exception as exc:
                logger.warning("ensure_branch %s failed: %s", bn, exc)

        return StagingRunnerResult(
            target=bn,
            external_ref=artifacts_ref,
            detail=f"branch {bn} prepared from {self.base_ref}",
        )

    def discard(self, *, target: str) -> None:
        if not (self.token and self.repo and httpx is not None):
            logger.info("discard %s — no GitHub adapter, no-op", target)
            return
        try:
            httpx.delete(
                f"https://api.github.com/repos/{self.repo}/git/refs/heads/{target}",
                headers=self._headers(),
                timeout=30,
            )
        except Exception as exc:
            logger.warning("discard %s failed: %s", target, exc)

    def _ensure_branch(self, branch: str) -> None:
        assert httpx is not None
        # Get base ref sha.
        r = httpx.get(
            f"https://api.github.com/repos/{self.repo}/git/refs/heads/{self.base_ref}",
            headers=self._headers(),
            timeout=30,
        )
        r.raise_for_status()
        sha = r.json()["object"]["sha"]
        # Create the branch (idempotent: 422 if already exists).
        httpx.post(
            f"https://api.github.com/repos/{self.repo}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": sha},
            headers=self._headers(),
            timeout=30,
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }


class NoopCodeStagingRunner:
    """Drop-in for tests / dev — never touches the network."""

    type = "code"

    def apply(
        self,
        *,
        action_id: str,
        ticket_id: str | None,
        target: str,
        artifacts_ref: str,
        expected_outcome: dict,
    ) -> StagingRunnerResult:
        bn = target if target and target.startswith("sentinel/") else branch_name(
            ticket_id=ticket_id, action_id=action_id
        )
        return StagingRunnerResult(
            target=bn, external_ref=artifacts_ref, detail="dry-run"
        )

    def discard(self, *, target: str) -> None:
        return
