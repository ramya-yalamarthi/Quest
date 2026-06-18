"""S2 — Backend software defect (Hybrid).

Happy: human accepts -> code applied to staging branch + CI -> generated
tests pass, regression passes, telemetry nominal, no correlated incidents
-> Promoted.

Negative: one generated test fails in CI -> Validating -> Failed -> Reverted
(branch auto-discarded) -> ticket routed to manual with bot's draft retained.
"""

from app.mitigation_safety.db.models import BotActionLog, StagingDeployment


def test_s2_happy_promotes(service_bundle, make_action):
    s = service_bundle
    action = make_action(state="APPROVED", category="software_defect", type="code")
    s["mock_ci"].set_default("success")

    from app.mitigation_safety.config import default_store
    default_store().override(
        confirm_to_promote={"_default": True, "software_defect": True}
    )

    stage = s["staging"].stage(
        action_id=action.action_id,
        type="code",
        target="sentinel/abc/def",
        artifacts_ref="diff:fix#123",
        expected_outcome={"component": "payments-api"},
        revert_handle_ref="rh-code-revert",
        actor="human:engineer-1",
    )
    s["db"].commit()
    vr = s["validation"].evaluate_now(stage.validation_id)
    s["db"].commit()
    assert vr.overall_status == "PASS"

    out = s["promotion"].promote(
        action_id=action.action_id, confirm=True, actor="human:engineer-1"
    )
    s["db"].commit()
    assert out.state == "PROMOTED"


def test_s2_failing_generated_test_reverts_and_discards(service_bundle, make_action):
    s = service_bundle
    action = make_action(state="APPROVED", category="software_defect", type="code")
    s["mock_ci"].script("generated_tests", "failure").script("regression_suite", "success")

    stage = s["staging"].stage(
        action_id=action.action_id,
        type="code",
        target="sentinel/abc/fail",
        artifacts_ref="diff:bad#123",
        expected_outcome={"component": "payments-api"},
        revert_handle_ref="rh-code-revert",
        actor="human:engineer-1",
    )
    s["db"].commit()
    vr = s["validation"].evaluate_now(stage.validation_id)
    s["db"].commit()
    assert vr.overall_status == "FAIL"

    fresh = s["db"].get(BotActionLog, action.action_id)
    assert fresh.state == "REVERTED"
    deployment = (
        s["db"].query(StagingDeployment)
        .filter(StagingDeployment.action_id == action.action_id)
        .one()
    )
    assert deployment.status == "REVERTED"
