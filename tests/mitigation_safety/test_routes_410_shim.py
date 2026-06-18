"""MS-26: superseded routes return 410 with a pointer."""

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    # We need the shim router specifically — building it alone avoids the
    # `require_human` dependency that the rest of the API uses.
    from app.mitigation_safety.api.shim_routes import router

    a = FastAPI()
    a.include_router(router)
    return a


def test_execute_returns_410(app):
    client = TestClient(app)
    resp = client.post("/mitigate/execute")
    assert resp.status_code == 410
    body = resp.json()
    assert "Gone" in body["detail"]["error"]
    assert "stage" in body["detail"]["msg"]


def test_rollback_returns_410(app):
    client = TestClient(app)
    resp = client.post("/mitigate/rollback")
    assert resp.status_code == 410
    body = resp.json()
    assert "revert" in body["detail"]["msg"]
