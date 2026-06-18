"""Invariant 8: revert is idempotent.

Re-issuing a revert that already completed is a no-op returning
`idempotent=True`. The registered revert handle is invoked at most once.
"""


def test_revert_twice_only_calls_handle_once(service_bundle, make_action):
    s = service_bundle
    action = make_action(state="APPROVED")
    s["mock_ci"].set_default("success")

    result = s["staging"].stage(
        action_id=action.action_id,
        type="config",
        target="staging-quota",
        artifacts_ref="cfg",
        expected_outcome={"component": "payments"},
        revert_handle_ref="rh-quota-restart",
        actor="human:42",
    )
    s["db"].commit()
    s["validation"].evaluate_now(result.validation_id)
    s["db"].commit()
    s["promotion"].promote(
        action_id=action.action_id, confirm=True, actor="human:42"
    )
    s["db"].commit()

    first = s["revert"].revert(action_id=action.action_id, reason="ops decision", actor="human:42")
    s["db"].commit()
    assert first.idempotent is False
    assert first.state == "ROLLEDBACK"

    second = s["revert"].revert(action_id=action.action_id, reason="duplicate request", actor="human:42")
    s["db"].commit()
    assert second.idempotent is True
    assert second.state == "ROLLEDBACK"

    # The revert handle function was invoked exactly once.
    assert s["revert_registry"].test_calls["n"] == 1


def test_revert_in_validating_succeeds(service_bundle, make_action):
    """Revert can fire while still Validating: action ends Reverted."""
    s = service_bundle
    action = make_action(state="APPROVED")
    s["mock_ci"].set_default("success")
    result = s["staging"].stage(
        action_id=action.action_id,
        type="code",
        target="sentinel/x",
        artifacts_ref="diff",
        expected_outcome={"component": "x"},
        revert_handle_ref="rh-code-revert",
        actor="human:42",
    )
    s["db"].commit()
    # Do NOT evaluate — manual abort while validating.
    out = s["revert"].revert(action_id=action.action_id, reason="manual abort", actor="human:42")
    s["db"].commit()
    assert out.state == "REVERTED"
