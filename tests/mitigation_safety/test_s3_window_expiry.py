"""S3 — Window expiry: never auto-promote.

Telemetry insufficient -> window passes without PASS -> Expired -> Reverted.
Assert no production effect ever occurred (no PROMOTED action, no
promoted_at timestamp).
"""

from datetime import datetime, timedelta, timezone

from app.mitigation_safety.db.models import BotActionLog, ValidationResult


def test_s3_no_production_effect_after_timeout(service_bundle, make_action):
    s = service_bundle
    action = make_action(state="APPROVED", category="capacity_quota", type="config")

    # Telemetry source returns insufficient — the check fails toward "need
    # human" but the test simulates indefinite PENDING by NOT evaluating until
    # window_end is in the past, then force-expiring.
    s["mock_telemetry"].insufficient("payments-quota")

    stage = s["staging"].stage(
        action_id=action.action_id,
        type="config",
        target="staging-quota-eu",
        artifacts_ref="quota:eu+200",
        expected_outcome={"component": "payments-quota"},
        revert_handle_ref="rh-quota-restart",
        actor="human:42",
    )
    s["db"].commit()

    # Push window into the past WITHOUT a PASS.
    vr = s["db"].get(ValidationResult, stage.validation_id)
    vr.window_end = datetime.now(timezone.utc) - timedelta(seconds=1)
    s["db"].add(vr)
    s["db"].commit()

    s["validation"].mark_expired(stage.validation_id)
    s["db"].commit()

    refreshed_vr = s["db"].get(ValidationResult, stage.validation_id)
    assert refreshed_vr.overall_status == "EXPIRED"
    assert refreshed_vr.promoted_at is None

    fresh = s["db"].get(BotActionLog, action.action_id)
    assert fresh.state == "REVERTED"

    # No PROMOTED record ever existed.
    all_actions = s["db"].query(BotActionLog).all()
    assert all(a.state != "PROMOTED" for a in all_actions)


def test_s3_expiry_via_worker_entrypoint(
    service_bundle, make_action, SessionMaker, mock_ci, mock_telemetry
):
    """#33: S3 routed through the actual `expiry_poller` worker entrypoint —
    not just the synchronous ValidationService.mark_expired call."""
    s = service_bundle
    from app.mitigation_safety.api.container import set_ci_runner, set_telemetry
    from app.mitigation_safety.staging.revert_handles import default_registry
    from app.mitigation_safety.worker import jobs as worker_jobs

    set_ci_runner(mock_ci.set_default("success"))
    set_telemetry(mock_telemetry)
    reg = default_registry()
    if not reg.has_tested("rh-quota-restart"):
        reg.register(
            ref="rh-quota-restart", description="t", procedure_name="p",
            fn=lambda payload: {"ok": True},
        )

    action = make_action(state="APPROVED", category="capacity_quota", type="config")
    s["mock_telemetry"].insufficient("payments-quota")
    stage = s["staging"].stage(
        action_id=action.action_id,
        type="config",
        target="staging-quota-eu",
        artifacts_ref="quota:eu+200",
        expected_outcome={"component": "payments-quota"},
        revert_handle_ref="rh-quota-restart",
        actor="human:42",
    )
    s["db"].commit()

    vr = s["db"].get(ValidationResult, stage.validation_id)
    vr.window_end = datetime.now(timezone.utc) - timedelta(seconds=1)
    s["db"].add(vr)
    s["db"].commit()

    worker_jobs.set_session_factory(SessionMaker)
    try:
        worker_jobs.expiry_poller(str(stage.validation_id))
    finally:
        worker_jobs.set_session_factory(None)

    # Force read from a fresh session — the worker's session is closed.
    fresh = SessionMaker()
    try:
        refreshed_vr = fresh.get(ValidationResult, stage.validation_id)
        assert refreshed_vr.overall_status == "EXPIRED"
        assert refreshed_vr.promoted_at is None
        fresh_action = fresh.get(BotActionLog, action.action_id)
        assert fresh_action.state == "REVERTED"
    finally:
        fresh.close()
