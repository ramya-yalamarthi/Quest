"""Invariant 2, MS-10: window expiry -> Expired -> Reverted, never auto-promote."""

from datetime import datetime, timedelta, timezone

from app.mitigation_safety.db.models import BotActionLog, ValidationResult


def test_expiry_marks_action_expired_and_reverts(service_bundle, make_action):
    s = service_bundle
    action = make_action(state="APPROVED")
    s["mock_ci"].set_default("success")

    result = s["staging"].stage(
        action_id=action.action_id,
        type="config",
        target="staging-quota",
        artifacts_ref="config:quota",
        expected_outcome={"component": "payments-api"},
        revert_handle_ref="rh-quota-restart",
        actor="human:42",
    )
    s["db"].commit()

    # Force window_end into the past.
    vr = s["db"].get(ValidationResult, result.validation_id)
    vr.window_end = datetime.now(timezone.utc) - timedelta(seconds=1)
    s["db"].add(vr)
    s["db"].commit()

    vr2 = s["validation"].mark_expired(result.validation_id)
    s["db"].commit()
    assert vr2.overall_status == "EXPIRED"

    fresh = s["db"].get(BotActionLog, action.action_id)
    # The action transitioned through EXPIRED; auto_revert.fire then drove it
    # to REVERTED via the test bundle's revert callable.
    assert fresh.state == "REVERTED"
    assert vr2.promoted_at is None
