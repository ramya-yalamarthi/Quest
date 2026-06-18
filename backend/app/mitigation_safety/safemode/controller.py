"""Safe Mode controller (MS-19..MS-23, invariant 5).

Hard rules enforced here:
- enter(scope, entered_by, reason): inserts an active row OR is a no-op if a
  matching active row already exists (idempotent).
- exit(scope, exited_by, reason):  REJECTS unless exited_by starts with
  `human:` (MS-22). Inactivates the active row by inserting a new row with
  active=false + exited_by/exited_at filled (the DB CHECK constraint forbids
  any other shape).
- is_held(category): True iff system scope OR `category:<name>` is active.
- on_unhandled_execution_error(category, exc): MS-23 — auto-enter per category.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.mitigation_safety.audit.service import MitigationAuditLogger
from app.mitigation_safety.db.models import SafeModeState
from app.mitigation_safety.domain.errors import SafeModeHumanRequired

logger = logging.getLogger("mitigation_safety.safemode")


SYSTEM_SCOPE = "system"


def category_scope(category: str) -> str:
    return f"category:{category}"


@dataclass(frozen=True)
class SafeModeEntry:
    scope: str
    active: bool
    entered_at: Optional[datetime]
    entered_by: Optional[str]
    exited_at: Optional[datetime]
    exited_by: Optional[str]
    reason: Optional[str]


class SafeModeController:
    """Service-layer controller. Caller owns the SQLAlchemy session.

    Audit writes are emitted via `MitigationAuditLogger`; the caller must
    commit the session after the call returns. Failures raise; no Safe Mode
    code path commits on its own.
    """

    def __init__(self, db: Session, audit: MitigationAuditLogger) -> None:
        self.db = db
        self.audit = audit

    # -- queries ---------------------------------------------------------------
    def _active_row(self, scope: str) -> Optional[SafeModeState]:
        return (
            self.db.query(SafeModeState)
            .filter(SafeModeState.scope == scope, SafeModeState.active.is_(True))
            .order_by(SafeModeState.entered_at.desc())
            .first()
        )

    def get(self, scope: str) -> SafeModeEntry:
        row = self._active_row(scope)
        if row is None:
            return SafeModeEntry(
                scope=scope,
                active=False,
                entered_at=None,
                entered_by=None,
                exited_at=None,
                exited_by=None,
                reason=None,
            )
        return _to_entry(row)

    def is_active(self, scope: str) -> bool:
        return self._active_row(scope) is not None

    def is_held(self, category: Optional[str]) -> bool:
        """True iff system OR category:<name> is active. None category => system only."""
        if self.is_active(SYSTEM_SCOPE):
            return True
        if category:
            return self.is_active(category_scope(category))
        return False

    def snapshot(self, categories: tuple[str, ...]) -> dict[str, SafeModeEntry]:
        out: dict[str, SafeModeEntry] = {SYSTEM_SCOPE: self.get(SYSTEM_SCOPE)}
        for cat in categories:
            out[category_scope(cat)] = self.get(category_scope(cat))
        return out

    # -- mutations -------------------------------------------------------------
    def enter(
        self,
        *,
        scope: str,
        entered_by: str,
        reason: str,
        action_id: uuid.UUID | str | None = None,
    ) -> SafeModeEntry:
        """Idempotent: re-entering an already-active scope is a no-op."""
        existing = self._active_row(scope)
        if existing is not None:
            return _to_entry(existing)

        row = SafeModeState(
            scope=scope,
            active=True,
            entered_by=entered_by,
            reason=reason,
        )
        self.db.add(row)
        self.db.flush()
        self.audit.record(
            action_id=action_id or _zero_uuid(),
            ticket_id=None,
            actor=entered_by,
            transition_type="safe_mode",
            from_state=None,
            to_state="ACTIVE",
            detail={"scope": scope, "reason": reason},
        )
        logger.warning("Safe Mode ENTER scope=%s by=%s reason=%s", scope, entered_by, reason)
        return _to_entry(row)

    def exit(
        self,
        *,
        scope: str,
        exited_by: str,
        reason: str,
        action_id: uuid.UUID | str | None = None,
    ) -> SafeModeEntry:
        """MS-22: exit MUST be a human actor. Reject guard:* / system:* exits."""
        if not exited_by.startswith("human:"):
            raise SafeModeHumanRequired(
                f"Safe Mode exit requires a human actor (got {exited_by!r})"
            )

        active = self._active_row(scope)
        if active is None:
            # Not currently held — return the (empty) snapshot; idempotent.
            return self.get(scope)

        # Mark the active row inactive AND record exit metadata. Note: the
        # CHECK constraint requires exited_at NOT NULL + exited_by LIKE 'human:%'
        # AND active=false. Doing this with an UPDATE on this row is fine — we
        # are NOT touching ms_audit_log here.
        active.active = False
        active.exited_at = datetime.now(timezone.utc)
        active.exited_by = exited_by
        self.db.add(active)
        self.db.flush()
        self.audit.record(
            action_id=action_id or _zero_uuid(),
            ticket_id=None,
            actor=exited_by,
            transition_type="safe_mode",
            from_state="ACTIVE",
            to_state="CLEARED",
            detail={"scope": scope, "reason": reason},
        )
        logger.warning("Safe Mode EXIT scope=%s by=%s reason=%s", scope, exited_by, reason)
        return _to_entry(active)

    # -- MS-23: auto-trip on unhandled execution error -------------------------
    def on_unhandled_execution_error(
        self, category: str, exc: BaseException
    ) -> SafeModeEntry:
        return self.enter(
            scope=category_scope(category),
            entered_by="guard:unhandled_execution_error",
            reason=f"{type(exc).__name__}: {exc}",
        )


def _to_entry(row: SafeModeState) -> SafeModeEntry:
    return SafeModeEntry(
        scope=row.scope,
        active=row.active,
        entered_at=row.entered_at,
        entered_by=row.entered_by,
        exited_at=row.exited_at,
        exited_by=row.exited_by,
        reason=row.reason,
    )


def _zero_uuid() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000000")
