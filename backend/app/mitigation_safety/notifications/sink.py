"""Engineer + lead notifications (MS-26).

Notifications fire on:
- validation failure
- window expiry / auto-revert
- guard-triggered rollback
- Safe Mode entry

Each notification carries action_id, ticket_id, triggering condition, and
resulting state. The default sink writes to stdout via the logger; an
optional webhook sink is wired for production via `NOTIFY_WEBHOOK_URL`.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional, Protocol

try:
    import httpx  # type: ignore
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore

logger = logging.getLogger("mitigation_safety.notifications")


@dataclass(frozen=True)
class Notification:
    kind: str           # 'validation_failed' | 'window_expired' | 'guard_rollback' | 'safe_mode_entered'
    action_id: Optional[str]
    ticket_id: Optional[str]
    triggering: str
    resulting_state: Optional[str]
    detail: dict


class NotificationSink(Protocol):
    def emit(self, n: Notification) -> None: ...


class LoggingNotificationSink:
    def emit(self, n: Notification) -> None:
        logger.warning(
            "[NOTIFY] %s action=%s ticket=%s triggering=%s state=%s detail=%s",
            n.kind,
            n.action_id,
            n.ticket_id,
            n.triggering,
            n.resulting_state,
            n.detail,
        )


class InMemoryNotificationSink:
    """Test sink — captures everything emitted."""

    def __init__(self) -> None:
        self.events: list[Notification] = []

    def emit(self, n: Notification) -> None:
        self.events.append(n)


def _webhook_url_safe(url: str) -> bool:
    """#20: refuse webhook URLs that target internal/loopback addresses
    or non-https schemes. The allowlist is opt-in via NOTIFY_WEBHOOK_ALLOWED_HOSTS
    (comma-separated); when unset, any https URL with a public-looking host
    is accepted (we still block localhost / RFC1918 / link-local)."""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    # Hard blocklist regardless of allowlist.
    blocked_exact = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
    if host in blocked_exact:
        return False
    # RFC1918 / link-local / metadata-service.
    blocked_prefixes = (
        "10.", "192.168.", "169.254.", "172.16.", "172.17.", "172.18.",
        "172.19.", "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
        "172.25.", "172.26.", "172.27.", "172.28.", "172.29.", "172.30.",
        "172.31.",
    )
    if any(host.startswith(p) for p in blocked_prefixes):
        return False
    # Optional positive allowlist.
    allowlist_env = os.getenv("NOTIFY_WEBHOOK_ALLOWED_HOSTS")
    if allowlist_env:
        allow = {h.strip().lower() for h in allowlist_env.split(",") if h.strip()}
        return host in allow
    return True


class WebhookNotificationSink:
    def __init__(self, url: str | None = None) -> None:
        self.url = url or os.getenv("NOTIFY_WEBHOOK_URL") or ""

    def emit(self, n: Notification) -> None:
        if not self.url or httpx is None:
            return
        if not _webhook_url_safe(self.url):
            logger.warning(
                "webhook URL rejected by safety policy: scheme/host not allowed"
            )
            return
        try:
            httpx.post(
                self.url,
                json={
                    "kind": n.kind,
                    "action_id": n.action_id,
                    "ticket_id": n.ticket_id,
                    "triggering": n.triggering,
                    "resulting_state": n.resulting_state,
                    "detail": n.detail,
                },
                timeout=10,
            )
        except Exception as exc:
            # #20: don't echo the raw exception (it can contain Slack/Teams
            # token fragments via the URL). Log the type only.
            logger.warning(
                "webhook notification failed: %s", type(exc).__name__
            )


def default_sink() -> NotificationSink:
    if os.getenv("NOTIFY_WEBHOOK_URL"):
        return WebhookNotificationSink()
    return LoggingNotificationSink()
