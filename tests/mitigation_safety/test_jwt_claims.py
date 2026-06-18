"""#22: every token carries verified `aud` and `iss` claims.

A token whose audience doesn't match the configured one is rejected at
decode time — that's the protection we want against cross-service replay.
"""

import pytest
from jose import jwt as jose_jwt

from app.auth.jwt import (
    JWT_AUDIENCE,
    JWT_ISSUER,
    create_access_token,
    decode_token,
)
from app.config import JWT_ALGORITHM, JWT_SECRET


def test_created_token_carries_aud_iss():
    token = create_access_token({"user_id": "alice"})
    # Decode without verification to inspect raw claims.
    raw = jose_jwt.get_unverified_claims(token)
    assert raw["aud"] == JWT_AUDIENCE
    assert raw["iss"] == JWT_ISSUER
    assert raw["user_id"] == "alice"


def test_decode_rejects_mismatched_audience():
    # Mint a token with a foreign audience, signed with the same secret.
    import time

    payload = {
        "user_id": "u",
        "exp": int(time.time()) + 600,
        "aud": "some-other-service",
        "iss": JWT_ISSUER,
    }
    bad = jose_jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    with pytest.raises(Exception):
        decode_token(bad)


def test_decode_rejects_missing_audience():
    import time

    payload = {
        "user_id": "u",
        "exp": int(time.time()) + 600,
        "iss": JWT_ISSUER,
        # no aud at all
    }
    bad = jose_jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    with pytest.raises(Exception):
        decode_token(bad)


def test_decode_rejects_mismatched_issuer():
    import time

    payload = {
        "user_id": "u",
        "exp": int(time.time()) + 600,
        "aud": JWT_AUDIENCE,
        "iss": "evil-issuer",
    }
    bad = jose_jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    with pytest.raises(Exception):
        decode_token(bad)


def test_round_trip_succeeds_with_default_claims():
    token = create_access_token({"user_id": "alice", "scopes": ["mitigation:read"]})
    claims = decode_token(token)
    assert claims["user_id"] == "alice"
    assert claims["aud"] == JWT_AUDIENCE
    assert claims["iss"] == JWT_ISSUER
