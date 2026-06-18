"""API dependencies.

`require_human(scopes=[...])`:
  Today wraps `app.auth.deps.get_current_user` (HS256 JWT) and returns a
  `HumanActor` whose `actor_id` starts with "human:" — that prefix is the
  contract MS-22 enforces. Tomorrow this dependency becomes a real
  Azure-AD / MSAL bearer validator without changing any route signature.

`get_db()` yields a SessionLocal scoped to the request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user


@dataclass(frozen=True)
class HumanActor:
    actor_id: str          # always "human:<user_id>"
    scopes: list[str]
    raw_claims: dict


def get_db() -> Session:
    # Import lazily so that test environments without psycopg2 (which only
    # exercise the dep itself via override) don't trigger engine creation.
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_human(scopes: Iterable[str] | None = None):
    """Returns a FastAPI dependency that yields a `HumanActor`.

    The dependency:
      * forces authentication via the existing bearer token validator,
      * REQUIRES an identifying claim (`user_id`, `sub`, or `email`) — a
        token without one is rejected 401 so MS-22 audit rows are never
        attributable to "human:anon" (#7),
      * normalizes the `scopes` claim (list, str, or OIDC space-delimited),
      * verifies any requested scopes are present,
      * prefixes the resulting `actor_id` with "human:" so SafeModeController
        can satisfy MS-22 unconditionally.
    """
    required = list(scopes or [])

    def _inner(current=Depends(get_current_user)) -> HumanActor:
        # `current` is the decoded JWT payload from app.auth.jwt.decode_token.
        user_id = (
            current.get("user_id")
            or current.get("sub")
            or current.get("email")
        )
        if not user_id:
            # Refuse to mint an audit-bearing identity for an anonymous token.
            raise HTTPException(
                status_code=401,
                detail={
                    "error": "no_identity_claim",
                    "msg": "token must carry user_id, sub, or email",
                },
            )
        granted = _normalize_scopes(current)
        missing = [s for s in required if s not in granted]
        if missing:
            raise HTTPException(
                status_code=403, detail={"error": "missing scopes", "missing": missing}
            )
        return HumanActor(
            actor_id=f"human:{user_id}",
            scopes=granted,
            raw_claims=current,
        )

    return _inner


def _normalize_scopes(claims: dict) -> list[str]:
    """Robustly extract scopes from a JWT payload.

    Accepts:
      - `scopes`: list[str] or single str
      - `scope`:  OIDC space-delimited str (legacy) or list
    Returns a deduped list of stripped non-empty scopes.
    """
    raw = claims.get("scopes")
    if raw is None:
        raw = claims.get("scope")
    if raw is None:
        return []
    if isinstance(raw, str):
        items = raw.split()
    elif isinstance(raw, (list, tuple)):
        items = []
        for entry in raw:
            if isinstance(entry, str):
                items.extend(entry.split())
    else:
        return []
    seen: dict[str, None] = {}
    for s in items:
        s = s.strip()
        if s and s not in seen:
            seen[s] = None
    return list(seen.keys())
