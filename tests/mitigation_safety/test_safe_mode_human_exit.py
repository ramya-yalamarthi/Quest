"""MS-22, invariant 5: Safe Mode exit MUST be by a human actor."""

import pytest

from app.mitigation_safety.audit.service import MitigationAuditLogger
from app.mitigation_safety.domain.errors import SafeModeHumanRequired
from app.mitigation_safety.safemode.controller import (
    SafeModeController,
    SYSTEM_SCOPE,
)


def test_guard_exit_rejected(db):
    ctrl = SafeModeController(db, MitigationAuditLogger(db))
    ctrl.enter(scope=SYSTEM_SCOPE, entered_by="guard:boot", reason="default")
    db.commit()

    with pytest.raises(SafeModeHumanRequired):
        ctrl.exit(scope=SYSTEM_SCOPE, exited_by="guard:override", reason="x")


def test_system_actor_exit_rejected(db):
    ctrl = SafeModeController(db, MitigationAuditLogger(db))
    ctrl.enter(scope=SYSTEM_SCOPE, entered_by="guard:boot", reason="default")
    db.commit()

    with pytest.raises(SafeModeHumanRequired):
        ctrl.exit(scope=SYSTEM_SCOPE, exited_by="system", reason="x")


def test_human_exit_succeeds(db):
    ctrl = SafeModeController(db, MitigationAuditLogger(db))
    ctrl.enter(scope=SYSTEM_SCOPE, entered_by="guard:boot", reason="default")
    db.commit()

    entry = ctrl.exit(scope=SYSTEM_SCOPE, exited_by="human:42", reason="ok now")
    db.commit()
    assert entry.active is False
    assert entry.exited_by == "human:42"
    assert not ctrl.is_active(SYSTEM_SCOPE)


def test_idempotent_re_enter(db):
    ctrl = SafeModeController(db, MitigationAuditLogger(db))
    ctrl.enter(scope=SYSTEM_SCOPE, entered_by="guard:boot", reason="first")
    ctrl.enter(scope=SYSTEM_SCOPE, entered_by="guard:other", reason="second")
    db.commit()
    # Only one active row should exist for SYSTEM_SCOPE.
    from app.mitigation_safety.db.models import (
        MitigationAuditLog,
        SafeModeState,
    )
    active = (
        db.query(SafeModeState)
        .filter(SafeModeState.scope == SYSTEM_SCOPE, SafeModeState.active.is_(True))
        .all()
    )
    assert len(active) == 1
    # The original entered_by survives.
    assert active[0].entered_by == "guard:boot"

    # And the audit log only carries ONE safe-mode entry for the system
    # scope. The second `enter()` was a no-op and must not write a duplicate
    # row.
    audit_rows = (
        db.query(MitigationAuditLog)
        .filter(MitigationAuditLog.transition_type == "safe_mode")
        .all()
    )
    system_rows = [r for r in audit_rows if (r.detail or {}).get("scope") == SYSTEM_SCOPE]
    assert len(system_rows) == 1, (
        f"expected exactly one system-scope safe-mode audit row, got {len(system_rows)}"
    )
