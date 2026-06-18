"""MS-16, MS-20: guard auto-trip enters Safe Mode + auto-reverts in-flight."""

from app.mitigation_safety.db.models import BotActionLog
from app.mitigation_safety.safemode.controller import category_scope


def test_validation_failure_rate_trips_safe_mode(service_bundle, make_action):
    s = service_bundle

    # Seed enough attempts + failures so the rate crosses 20% with min_samples=1.
    for _ in range(3):
        s["rolling"].record(signal="attempt", category="capacity_quota")
        s["rolling"].record(signal="validation_failed", category="capacity_quota")
    s["db"].commit()

    # Spin up one in-flight action that should be auto-reverted on trip.
    in_flight = make_action(state="APPROVED")
    s["mock_ci"].set_default("success")
    result = s["staging"].stage(
        action_id=in_flight.action_id,
        type="code",
        target="sentinel/x",
        artifacts_ref="diff",
        expected_outcome={"component": "x"},
        revert_handle_ref="rh-code-revert",
        actor="human:42",
    )
    s["db"].commit()

    verdict = s["guard"].evaluate("capacity_quota")
    s["db"].commit()

    assert verdict.safe_mode_entered is True
    assert verdict.triggering_signal == "validation_failed"
    assert s["safe_mode"].is_active(category_scope("capacity_quota"))
    # Notification was emitted.
    kinds = [n.kind for n in s["notifier"].events]
    assert "safe_mode_entered" in kinds

    refreshed = s["db"].get(BotActionLog, in_flight.action_id)
    assert refreshed.state == "REVERTED"
