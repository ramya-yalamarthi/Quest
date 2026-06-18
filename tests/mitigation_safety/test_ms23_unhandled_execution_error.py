"""MS-23: any unhandled mitigation-execution error enters Safe Mode for the
affected category (#34).

We simulate the failure mode two ways:
  - StagingService.stage() — a runner.apply that raises must trip Safe Mode
    in an isolated session so the trip persists even though the outer
    transaction rolls back.
  - SafeModeController.on_unhandled_execution_error — the controller path
    used by both stage and promote on the catch.
"""

from app.mitigation_safety.audit.service import MitigationAuditLogger
from app.mitigation_safety.safemode.controller import (
    SafeModeController,
    category_scope,
)


def test_on_unhandled_execution_error_trips_per_category(db):
    audit = MitigationAuditLogger(db)
    ctrl = SafeModeController(db, audit)
    try:
        raise ValueError("simulated runner explosion")
    except ValueError as exc:
        ctrl.on_unhandled_execution_error("capacity_quota", exc)
    db.commit()
    assert ctrl.is_active(category_scope("capacity_quota"))
    entry = ctrl.get(category_scope("capacity_quota"))
    assert entry.entered_by == "guard:unhandled_execution_error"
    assert "ValueError" in (entry.reason or "")


def test_persist_safe_mode_in_isolation_writes_via_real_session(
    db, SessionMaker, make_action
):
    """The isolation path the service uses must persist via a brand-new
    SessionLocal so the trip survives the caller's rollback.

    We install the test sessionmaker via the documented test seam so the
    helper writes into the same SQLite engine the test inspects.
    """
    from app.mitigation_safety.staging.service import (
        _persist_safe_mode_in_isolation,
        set_isolation_session_factory,
    )

    set_isolation_session_factory(SessionMaker)
    try:
        _persist_safe_mode_in_isolation(
            category="software_defect", exc=RuntimeError("boom")
        )
    finally:
        set_isolation_session_factory(None)

    # The helper opened+closed its own session. Read back from a fresh one.
    fresh = SessionMaker()
    try:
        ctrl = SafeModeController(fresh, MitigationAuditLogger(fresh))
        assert ctrl.is_active(category_scope("software_defect"))
    finally:
        fresh.close()
