from datetime import datetime, timedelta, timezone
import logging
import os

from jose import jwt
from app.config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_MINUTES

logger = logging.getLogger("app.auth.jwt")


# #22 (part 1): a committed default like "dev_only_change_me" must never be
# used outside an explicit-dev environment. APP_ENV defaults to "dev"; any
# other value (`staging`, `prod`) makes startup REFUSE to mint tokens with
# the default secret. The check runs at module import time so a misconfigured
# deploy fails fast instead of silently signing tokens with the public
# secret.
_DEV_DEFAULTS = {"dev_only_change_me"}
APP_ENV = (os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "dev").lower()
if APP_ENV not in ("dev", "development", "local", "test") and JWT_SECRET in _DEV_DEFAULTS:
    raise RuntimeError(
        "JWT_SECRET is set to the committed dev default outside a dev "
        f"environment (APP_ENV={APP_ENV!r}). Refusing to start; rotate the "
        "secret before deploying."
    )


# #22 (part 2): every token carries `aud` (audience) and `iss` (issuer)
# claims, and `decode_token` verifies them. Without these, a token minted
# for one service could be replayed against another that happens to share
# the same secret — a real risk once we have more than one consumer.
#
# Configurable via env so dev and CI can override without code changes.
# Default audience matches the service name; default issuer matches the
# deploy environment so logs are unambiguous.
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "sentinel-mitigation-safety")
JWT_ISSUER = os.getenv("JWT_ISSUER", f"sentinel-{APP_ENV}")


def create_access_token(claims: dict) -> str:
    """Mint a bearer token.

    Adds the standard `iat`, `nbf`, `exp`, `aud`, `iss` claims unless the
    caller has already supplied them (the override is useful in tests that
    want to assert audience-mismatch handling). Caller's claims win on
    every key so existing call sites (`user_id`, `scopes`) keep working.
    """
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {
        "iat": now,
        "nbf": now,
        "exp": exp,
        "aud": JWT_AUDIENCE,
        "iss": JWT_ISSUER,
        **claims,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Verify signature, expiry, audience, and issuer.

    A token without the configured `aud` or `iss` (or with mismatched
    values) raises `JWTClaimsError` / `JWTError`, which the existing
    `get_current_user` dependency surfaces as 401.

    `python-jose` silently accepts a token with NO `aud` claim even when
    we pass `audience=...`, so we explicitly enforce presence + match.
    """
    claims = jwt.decode(
        token,
        JWT_SECRET,
        algorithms=[JWT_ALGORITHM],
        audience=JWT_AUDIENCE,
        issuer=JWT_ISSUER,
        # `require_*` ensures jose raises if the claim is absent altogether.
        options={"require_aud": True, "require_iss": True},
    )
    # Belt-and-braces: re-check in case the underlying lib's option set
    # changes across versions.
    if claims.get("aud") != JWT_AUDIENCE:
        from jose.exceptions import JWTClaimsError
        raise JWTClaimsError(f"audience claim mismatch: {claims.get('aud')!r}")
    if claims.get("iss") != JWT_ISSUER:
        from jose.exceptions import JWTClaimsError
        raise JWTClaimsError(f"issuer claim mismatch: {claims.get('iss')!r}")
    return claims
