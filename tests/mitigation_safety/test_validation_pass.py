"""Happy-path validation: all checks PASS -> overall_status=PASS, no auto-revert."""


def test_pass_path_marks_validation_pass(service_bundle, make_action):
    s = service_bundle
    action = make_action(state="APPROVED")
    s["mock_ci"].script("generated_tests", "success").script("regression_suite", "success")
    result = s["staging"].stage(
        action_id=action.action_id,
        type="code",
        target="sentinel/test/x",
        artifacts_ref="diff:abc",
        expected_outcome={"component": "payments-api"},
        revert_handle_ref="rh-code-revert",
        actor="human:42",
    )
    s["db"].commit()

    vr = s["validation"].evaluate_now(result.validation_id)
    s["db"].commit()
    assert vr.overall_status == "PASS"
    statuses = {c["name"]: c["status"] for c in vr.checks}
    assert statuses["generated_tests"] == "PASS"
    assert statuses["regression_suite"] == "PASS"
    assert statuses["telemetry_bounds"] == "PASS"
    assert statuses["correlated_incidents"] == "PASS"
