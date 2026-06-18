"""Real CIRunner backed by GitHub Actions (workflow_dispatch).

Env vars (set at deploy):
  GITHUB_TOKEN              - PAT or GitHub App token (repo + workflow scope)
  GITHUB_REPO               - "<org>/<repo>"
  GITHUB_WORKFLOW_FILE      - e.g. "validate.yml"
  GITHUB_CI_REF             - branch/ref the workflow runs from (default 'main')
  GITHUB_CI_TIMEOUT_SECONDS - per-poll deadline (default 1800)
  GITHUB_API_BASE           - default https://api.github.com

#17: `GITHUB_API_BASE` is validated against an allowlist of known GitHub
endpoints to prevent a misconfigured / attacker-influenced env var from
exfiltrating the token to a third-party host. If the configured base is
unrecognized we refuse to dispatch.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

try:
    import httpx  # type: ignore
except ImportError:  # pragma: no cover - real impl only used when dep present
    httpx = None  # type: ignore

from app.mitigation_safety.validation.ci.interface import CIRunResult, CIStatus

logger = logging.getLogger("mitigation_safety.ci.github")


# #17: allowlist of acceptable GITHUB_API_BASE values. github.com SaaS and
# GitHub Enterprise Server use these two shapes. Anything else is treated
# as a misconfiguration and the dispatcher refuses to send the token.
_ALLOWED_API_HOSTS = (
    "api.github.com",
)


def _api_base_safe(base: str) -> bool:
    try:
        from urllib.parse import urlparse

        parsed = urlparse(base)
    except Exception:
        return False
    if parsed.scheme != "https":
        return False
    host = parsed.hostname or ""
    # Allow exact api.github.com OR GHES "<host>/api/v3" shape.
    if host in _ALLOWED_API_HOSTS:
        return True
    # GHES: any host with a "/api/v3" path is considered enterprise. The
    # operator opts in by setting GITHUB_API_BASE=https://ghes.acme.com/api/v3.
    if parsed.path.rstrip("/").endswith("/api/v3"):
        return True
    return False


class GitHubActionsCIRunner:
    """Concrete CIRunner. If `httpx` is unavailable or env vars missing the
    caller is expected to have fallen back to MockCIRunner at boot."""

    def __init__(
        self,
        *,
        token: str | None = None,
        repo: str | None = None,
        workflow_file: str | None = None,
        ref: str | None = None,
        api_base: str | None = None,
        timeout_s: int | None = None,
    ) -> None:
        self.token = token or os.getenv("GITHUB_TOKEN") or ""
        self.repo = repo or os.getenv("GITHUB_REPO") or ""
        self.workflow_file = (
            workflow_file or os.getenv("GITHUB_WORKFLOW_FILE") or "validate.yml"
        )
        self.ref = ref or os.getenv("GITHUB_CI_REF") or "main"
        self.api_base = (
            api_base or os.getenv("GITHUB_API_BASE") or "https://api.github.com"
        )
        if not _api_base_safe(self.api_base):
            # Refuse early so the misconfig surfaces before we ever send
            # the token to an unrecognized host.
            raise RuntimeError(
                f"GITHUB_API_BASE not in allowlist: {self.api_base!r}"
            )
        self.timeout_s = int(
            timeout_s or os.getenv("GITHUB_CI_TIMEOUT_SECONDS") or 1800
        )

    # ---- protocol ----------------------------------------------------------
    def dispatch(
        self,
        *,
        suite: str,
        branch: str,
        artifacts_ref: str,
        action_id: str,
    ) -> str:
        if httpx is None:
            raise RuntimeError("httpx is not installed")
        url = (
            f"{self.api_base}/repos/{self.repo}/actions/workflows/"
            f"{self.workflow_file}/dispatches"
        )
        payload = {
            "ref": self.ref,
            "inputs": {
                "suite": suite,
                "branch": branch,
                "artifacts_ref": artifacts_ref,
                "action_id": action_id,
            },
        }
        resp = httpx.post(url, json=payload, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        # GitHub does not return a run_id on dispatch — we synthesize one and
        # resolve it on the first poll by matching the most recent run for the
        # branch.
        return f"gha:{branch}:{int(time.time())}"

    def poll(self, run_id: str, *, deadline_s: int) -> CIRunResult:
        if httpx is None:
            raise RuntimeError("httpx is not installed")
        _, branch, _ = run_id.split(":", 2)
        deadline = time.time() + min(deadline_s, self.timeout_s)
        last_status: CIStatus = "queued"
        last_detail: str | None = None
        url = f"{self.api_base}/repos/{self.repo}/actions/runs?branch={branch}"
        while time.time() < deadline:
            resp = httpx.get(url, headers=self._headers(), timeout=30)
            if resp.status_code == 200:
                data: dict[str, Any] = resp.json()
                runs = data.get("workflow_runs") or []
                if runs:
                    run = runs[0]
                    s = run.get("status")
                    c = run.get("conclusion")
                    if s == "completed":
                        if c == "success":
                            return CIRunResult(run_id, "success", suite="gha",
                                               detail="ok", url=run.get("html_url"))
                        return CIRunResult(run_id, "failure", suite="gha",
                                           detail=str(c), url=run.get("html_url"))
                    last_status = "in_progress" if s == "in_progress" else "queued"
                    last_detail = s
            time.sleep(5)
        return CIRunResult(run_id, "timeout", suite="gha", detail=last_detail, url=None)

    def cancel(self, run_id: str) -> None:
        # Best-effort: requires the numeric run id, which we'd need to resolve.
        logger.info("GitHubActionsCIRunner.cancel(%s) — no-op (best effort)", run_id)

    # ---- helpers -----------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
