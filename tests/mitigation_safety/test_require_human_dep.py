"""MS-20: require_human prefixes the actor_id with 'human:' and enforces scopes.

Also verifies the fixes from the code-review pass:
  #7  — tokens without an identity claim are rejected 401 (no "human:anon")
  #16 — the scopes claim accepts list, single str, OIDC space-delimited str
"""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.mitigation_safety.api.deps import HumanActor, require_human


def _app() -> FastAPI:
    a = FastAPI()

    @a.get("/whoami")
    def whoami(actor: HumanActor = Depends(require_human(scopes=["mitigation:read"]))):
        return {"actor_id": actor.actor_id, "scopes": actor.scopes}

    @a.get("/safemode-act")
    def safemode_act(
        actor: HumanActor = Depends(require_human(scopes=["mitigation:safemode"])),
    ):
        return {"actor_id": actor.actor_id}

    return a


def test_unauthenticated_returns_4xx():
    client = TestClient(_app())
    resp = client.get("/whoami")
    assert resp.status_code in (401, 403)


def test_missing_scope_returns_403():
    client = TestClient(_app())
    token = create_access_token({"user_id": "user-99", "scopes": ["mitigation:read"]})
    resp = client.get(
        "/safemode-act", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403


def test_valid_token_yields_human_actor():
    client = TestClient(_app())
    token = create_access_token({"user_id": "user-99", "scopes": ["mitigation:read"]})
    resp = client.get(
        "/whoami", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["actor_id"] == "human:user-99"
    assert "mitigation:read" in body["scopes"]


# ---- #7: no identity → 401 (no human:anon) --------------------------------

def test_token_without_identity_claim_returns_401():
    client = TestClient(_app())
    token = create_access_token({"scopes": ["mitigation:read"]})  # no user_id/sub/email
    resp = client.get(
        "/whoami", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["detail"]["error"] == "no_identity_claim"


def test_token_with_sub_claim_accepted():
    client = TestClient(_app())
    token = create_access_token({"sub": "alice", "scopes": ["mitigation:read"]})
    resp = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["actor_id"] == "human:alice"


# ---- #16: scopes-claim normalisation --------------------------------------

def test_scopes_can_be_oidc_space_delimited_string():
    client = TestClient(_app())
    # OIDC-style: `scope` claim is a space-delimited string, not a list.
    token = create_access_token(
        {"sub": "u", "scope": "mitigation:read mitigation:safemode"}
    )
    resp = client.get("/safemode-act", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_scopes_can_be_single_string():
    client = TestClient(_app())
    token = create_access_token({"sub": "u", "scopes": "mitigation:read"})
    resp = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert "mitigation:read" in resp.json()["scopes"]
