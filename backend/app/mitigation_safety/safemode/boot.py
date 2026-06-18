"""Default-on Safe Mode at every start/restart (MS-15, MS-23, invariant 5).

Called from `app.mitigation_safety.startup.on_startup`. Idempotent.

Behavior:
- If `safe_mode_default_on_start=False` (configurable), this is a no-op.
- Otherwise: for the system scope AND each configured category, ensure there
  is an active SafeModeState row with `entered_by="guard:boot"`. Existing
  active rows are left alone — we never overwrite operator state.

There is no code path that auto-exits Safe Mode (MS-22, invariant 5).
"""

from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy.orm import Session

from app.mitigation_safety.audit.service import MitigationAuditLogger
from app.mitigation_safety.config import MitigationConfig
from app.mitigation_safety.safemode.controller import (
    SYSTEM_SCOPE,
    SafeModeController,
    category_scope,
)

logger = logging.getLogger("mitigation_safety.safemode.boot")


def ensure_default_on(
    db: Session,
    *,
    cfg: MitigationConfig,
    categories: Iterable[str] | None = None,
) -> None:
    if not cfg.safe_mode_default_on_start:
        logger.info("safe_mode_default_on_start=False; skipping boot enforcement")
        return

    audit = MitigationAuditLogger(db)
    ctrl = SafeModeController(db, audit)

    scopes = [SYSTEM_SCOPE] + [
        category_scope(c) for c in (categories or cfg.categories)
    ]
    for scope in scopes:
        if not ctrl.is_active(scope):
            ctrl.enter(
                scope=scope,
                entered_by="guard:boot",
                reason="default-on at start (MS-23)",
            )
    db.commit()
