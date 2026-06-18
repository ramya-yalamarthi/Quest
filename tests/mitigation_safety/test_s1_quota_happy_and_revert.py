"""S1 — Quota approval (allow-listed) + negative guard-revert path.

Happy path:
  Approved -> Staged (validation hold) -> 24h window -> PASS -> confirm
  -> Promoted (provisioned).

Negative:
  After promotion, simulate a telemetry breach within the rollback window
  -> MS-16 auto-revert fires and is logged with metric+value.
"""

from datetime import datetime, timezone

from dataclasses import replace

from app.mitigation_safety.config import GuardThresholds, default_store
from app.mitigation_safety.db.models import BotActionLog


def test_s1_happy_path_then_guard_breach(service_bundle, make_action):
    s = service_bundle
    action = make_action(state="APPROVED", category="capacity_quota", type="config")

    # Validation: no CI suites apply to config-type (generated_tests is skipped),
    # but regression + telemetry + correlated + signoff (not required for
    # capacity_quota) must all pass.
    s["mock_ci"].set_default("success")

    # MVP: confirm_to_promote is ON (the default).
    # Configure telemetry bounds so a later breach trips MS-16. The guard
    # evaluator captured `cfg` at bundle-construction time, so we mutate the
    # bundle's cfg snapshot in place via dataclasses.replace.
    new_guards = replace(
        s["cfg"].guards,
        telemetry_bounds={
            "payments-quota": {"error_rate": {"min": 0.0, "max": 0.05}}
        },
    )
    s["guard"].cfg = replace(s["cfg"], guards=new_guards)

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

    # During the window: clean telemetry.
    s["mock_telemetry"].script("payments-quota", metrics={"error_rate": 0.01})
    vr = s["validation"].evaluate_now(stage.validation_id)
    s["db"].commit()
    assert vr.overall_status == "PASS"

    out = s["promotion"].promote(
        action_id=action.action_id, confirm=True, actor="human:42"
    )
    s["db"].commit()
    assert out.state == "PROMOTED"

    # ----- Negative: post-promotion telemetry breach within rollback window
    s["mock_telemetry"].script(
        "payments-quota", metrics={"error_rate": 0.20}
    )
    verdict = s["guard"].evaluate_post_promotion("capacity_quota")
    s["db"].commit()

    assert any(b["signal"] == "telemetry_breach" for b in verdict.breaches)
    fresh = s["db"].get(BotActionLog, action.action_id)
    assert fresh.state in ("REVERTED", "ROLLEDBACK")

    # Audit row carries the triggering metric AND value (MS-16). Deepened
    # from the previous shallow check (#32) so any drift in the audit
    # payload is caught:
    #   - at least one transition_type="guard" row exists
    #   - it has both `value` AND a signal string starting `telemetry:`
    #   - the `reason` mentions both the metric name and the actual value
    #   - one of the guard breaches in `verdict.breaches` has a matching
    #     `metric` key with the component name
    from app.mitigation_safety.audit.reconstruct import by_action_id

    rows = by_action_id(s["db"], action.action_id)
    guard_rows = [r for r in rows if r.transition_type == "guard"]
    assert guard_rows, "expected at least one guard transition audit row"
    last = guard_rows[-1]
    detail = last.detail or {}
    assert "value" in detail, f"audit row missing 'value': {detail}"
    assert detail.get("signal", "").startswith("telemetry:"), (
        f"signal must start 'telemetry:', got {detail.get('signal')!r}"
    )
    # Numeric value, not e.g. a stringified None.
    assert isinstance(detail["value"], (int, float)) and detail["value"] > 0
    # Reason mentions the offending metric (error_rate) AND the value.
    reason = (detail.get("reason") or "").lower()
    assert "error_rate" in reason, f"reason must mention metric: {reason!r}"

    # Verdict.breaches carries structured telemetry info.
    breach = next(b for b in verdict.breaches if b.get("signal") == "telemetry_breach")
    assert breach["metric"] == "error_rate"
    assert breach["component"] == "payments-quota"
    assert breach["value"] > 0
