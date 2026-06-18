"""Invariant 3: a failing check auto-reverts (Validating -> Failed -> Reverted)."""

from app.mitigation_safety.db.models import BotActionLog


def test_failing_generated_tests_auto_reverts(service_bundle, make_action):
    s = service_bundle
    action = make_action(state="APPROVED")

    # Script: generated_tests FAIL, regression PASS
    s["mock_ci"].script("generated_tests", "failure")
    s["mock_ci"].script("regression_suite", "success")

    result = s["staging"].stage(
        action_id=action.action_id,
        type="code",
        target="sentinel/test/fail",
        artifacts_ref="diff:fail",
        expected_outcome={"component": "payments-api"},
        revert_handle_ref="rh-code-revert",
        actor="human:42",
    )
    s["db"].commit()

    vr = s["validation"].evaluate_now(result.validation_id)
    s["db"].commit()

    assert vr.overall_status == "FAIL"
    fresh = s["db"].get(BotActionLog, action.action_id)
    assert fresh.state == "REVERTED"
