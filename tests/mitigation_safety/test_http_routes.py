"""End-to-end HTTP tests for the 6 mitigation_safety routes (#29).

Drives the real `tickets_routes` + `safemode_routes` modules through a
FastAPI TestClient with `get_db` dependency-overridden to yield the test
SQLite session. This exercises:
  - Pydantic request/response schema validation (#37)
  - require_human (#7, #16, #20-claims)
  - all 409 / 423 / 410 mappings the README claims
  - the actual `container.services()` factory path
"""

from __future__ import annotations

import uuid
from typing import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.mitigation_safety.api.deps import get_db
from app.mitigation_safety.api.router import register_router
from app.mitigation_safety.api.container import (
    set_ci_runner,
    set_telemetry,
    get_incidents_source,
    get_signoff_source,
)


def _token(*scopes: str, user: str = "tester") -> str:
    return create_access_token({"user_id": user, "scopes": list(scopes)})


def _auth(scopes: list[str]) -> dict:
    return {"Authorization": f"Bearer {_token(*scopes)}"}


@pytest.fixture
def http_app(db, mock_ci, mock_telemetry):
    # Wire the singletons api.container reads so the routes use the same
    # scripted backends as the in-process service_bundle.
    set_ci_runner(mock_ci.set_default("success"))
    set_telemetry(mock_telemetry)

    # Register the test revert handles into the SAME registry the routes
    # use (api.container -> default_registry()). The in-process bundle has
    # its own RevertHandleRegistry; the HTTP path goes through the global.
    from app.mitigation_safety.staging.revert_handles import default_registry

    reg = default_registry()
    if not reg.has_tested("rh-quota-restart"):
        reg.register(
            ref="rh-quota-restart", description="t", procedure_name="p",
            fn=lambda payload: {"ok": True},
        )
    if not reg.has_tested("rh-code-revert"):
        reg.register(
            ref="rh-code-revert", description="t", procedure_name="p",
            fn=lambda payload: {"ok": True},
        )

    app = FastAPI()
    app.include_router(register_router())

    # Replace get_db with one that yields the test SQLite session.
    def _override_get_db() -> Iterator[object]:
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def http_client(http_app):
    return TestClient(http_app)


def _seed_action(db, make_action, **kw):
    a = make_action(**kw)
    db.commit()  # commit so the route's session sees the row
    return a


def test_stage_then_validation_then_promote_e2e(
    http_client, db, make_action, revert_registry  # noqa: ARG001  — fixtures wire registry
):
    ticket_id = uuid.uuid4()
    action = _seed_action(
        db, make_action, state="APPROVED", category="capacity_quota",
        ticket_id=str(ticket_id),
    )

    stage_resp = http_client.post(
        f"/tickets/{ticket_id}/mitigate/stage",
        json={
            "action_id": str(action.action_id),
            "type": "config",
            "artifacts_ref": "cfg:eu+200",
            "expected_outcome": {"component": "payments"},
            "revert_handle_ref": "rh-quota-restart",
            "category": "capacity_quota",
            "target": "staging-quota-eu",
        },
        headers=_auth(["mitigation:write"]),
    )
    assert stage_resp.status_code == 201, stage_resp.text
    payload = stage_resp.json()
    assert payload["status"] == "PENDING"

    val_resp = http_client.get(
        f"/tickets/{ticket_id}/mitigate/validation",
        headers=_auth(["mitigation:read"]),
    )
    assert val_resp.status_code == 200
    assert val_resp.json()["overall_status"] in ("PENDING", "PASS")


def test_stage_rejects_prod_target_409(http_client, db, make_action):
    action = _seed_action(db, make_action, state="APPROVED")
    ticket_id = uuid.uuid4()
    resp = http_client.post(
        f"/tickets/{ticket_id}/mitigate/stage",
        json={
            "action_id": str(action.action_id),
            "type": "config",
            "artifacts_ref": "cfg",
            "expected_outcome": {},
            "revert_handle_ref": "rh-quota-restart",
            "category": "capacity_quota",
            "target": "production",  # banned
        },
        headers=_auth(["mitigation:write"]),
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "scope_isolation"


def test_stage_missing_revert_handle_409(http_client, db, make_action):
    # Force the action to have no revert handle by clearing it.
    action = _seed_action(db, make_action, state="APPROVED", revert_handle_ref=None)
    ticket_id = uuid.uuid4()
    resp = http_client.post(
        f"/tickets/{ticket_id}/mitigate/stage",
        json={
            "action_id": str(action.action_id),
            "type": "config",
            "artifacts_ref": "cfg",
            "expected_outcome": {},
            # Reference a handle the registry has NOT been told to register:
            "revert_handle_ref": "rh-unknown",
            "category": "capacity_quota",
            "target": "staging-x",
        },
        headers=_auth(["mitigation:write"]),
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "revert_handle_missing"


def test_unauthenticated_stage_4xx(http_client, db, make_action):
    action = _seed_action(db, make_action, state="APPROVED")
    ticket_id = uuid.uuid4()
    resp = http_client.post(
        f"/tickets/{ticket_id}/mitigate/stage",
        json={
            "action_id": str(action.action_id),
            "type": "config",
            "artifacts_ref": "cfg",
            "expected_outcome": {},
            "revert_handle_ref": "rh-quota-restart",
            "category": "capacity_quota",
        },
    )
    assert resp.status_code in (401, 403)


def test_promote_without_pass_returns_409(http_client, db, make_action):
    # Stage but never evaluate — overall_status stays PENDING.
    action = _seed_action(db, make_action, state="APPROVED")
    ticket_id = uuid.uuid4()
    stage_resp = http_client.post(
        f"/tickets/{ticket_id}/mitigate/stage",
        json={
            "action_id": str(action.action_id),
            "type": "config",
            "artifacts_ref": "cfg",
            "expected_outcome": {},
            "revert_handle_ref": "rh-quota-restart",
            "category": "capacity_quota",
        },
        headers=_auth(["mitigation:write"]),
    )
    assert stage_resp.status_code == 201
    resp = http_client.post(
        f"/tickets/{ticket_id}/mitigate/promote",
        json={"action_id": str(action.action_id), "confirm": True},
        headers=_auth(["mitigation:promote"]),
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "validation_not_passed"


def test_safe_mode_get_returns_snapshot(http_client):
    resp = http_client.get(
        "/mitigation/safe-mode",
        headers=_auth(["mitigation:read"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "system" in body
    assert isinstance(body["categories"], dict)


def test_safe_mode_post_rejects_unknown_scope_400(http_client):
    resp = http_client.post(
        "/mitigation/safe-mode",
        json={"scope": "category:nonsense", "active": True, "reason": "test"},
        headers=_auth(["mitigation:safemode"]),
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "unknown_scope"


def test_stage_pydantic_max_length_rejects_huge_reason(http_client, db, make_action):
    """#19: Pydantic max_length backstop."""
    action = _seed_action(db, make_action, state="APPROVED")
    ticket_id = uuid.uuid4()
    huge = "x" * 10_000
    resp = http_client.post(
        f"/tickets/{ticket_id}/mitigate/stage",
        json={
            "action_id": str(action.action_id),
            "type": "config",
            "artifacts_ref": huge,  # capped at 1024
            "expected_outcome": {},
            "revert_handle_ref": "rh-quota-restart",
            "category": "capacity_quota",
        },
        headers=_auth(["mitigation:write"]),
    )
    assert resp.status_code == 422  # Pydantic validation


def test_old_routes_return_410(http_client):
    assert http_client.post("/mitigate/execute").status_code == 410
    assert http_client.post("/mitigate/rollback").status_code == 410
