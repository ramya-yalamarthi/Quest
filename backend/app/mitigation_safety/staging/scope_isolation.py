"""Staging isolation check (MS-11, invariant 7).

Hardened against regex bypasses surfaced by code review:
  prod.example.com   — '.' is not a recognised word boundary
  ' prod' / 'prod '  — leading/trailing whitespace evades anchors
  prod1              — alphanum suffix evades the boundary
  prod\\xad          — soft-hyphen / combining marks evade ASCII patterns
  PROD               — case
  pr0d / pr0ductn    — leetspeak (we don't try to defend against this; a
                       positive allowlist is the right tool for that — see
                       README "Deferred items").

The verifier:
  1. Unicode-normalizes target + artifacts_ref to NFKC.
  2. Removes all whitespace + soft-hyphen + zero-width chars.
  3. Lowercases.
  4. Tokenizes on any non-alphanumeric run, then matches BANNED_TOKENS
     against each token (so `prod` matches `prod`, `prod1`, `prod-eu` but
     NOT `nonprod` — `nonprod` becomes one token).
  5. Falls back to the substring-style patterns ONLY for full-string
     matches (`main`, `master`, `live`) to catch the obvious cases.

Failing this check raises ScopeIsolationViolation, which the API layer
maps to 409.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable

from app.mitigation_safety.domain.errors import ScopeIsolationViolation


# Token-level bans: each banned token, ANY occurrence in a normalized
# token, is rejected. Tokens are derived by splitting on non-alphanumerics.
BANNED_TOKENS: tuple[str, ...] = (
    "prod",
    "production",
    "live",
    "prd",          # common abbreviation
    "prodaccount",  # legacy spelling used in some envs
)

# Exact-string-only bans: must match the whole normalized string.
BANNED_EXACT: tuple[str, ...] = (
    "main",
    "master",
)

# Backwards-compat: the previous version of this file exposed regex
# patterns that downstream tests (and any in-repo consumers) might still
# reference. We keep the symbol but it is no longer the primary mechanism.
DEFAULT_BLOCKED_PATTERNS: tuple[str, ...] = tuple(
    [rf"\b{re.escape(t)}\b" for t in BANNED_TOKENS] + [rf"^{re.escape(t)}$" for t in BANNED_EXACT]
)


# Characters stripped from the input before tokenization.
_STRIP_CATEGORIES = {"Cf", "Zs"}  # format chars + space separators
_STRIP_EXTRA = {"­", "​", "‌", "‍", "﻿"}


def _normalize(value: str) -> str:
    """NFKC-normalize, strip format + whitespace + soft-hyphens, lowercase."""
    nf = unicodedata.normalize("NFKC", value)
    out = []
    for ch in nf:
        if ch in _STRIP_EXTRA:
            continue
        if unicodedata.category(ch) in _STRIP_CATEGORIES:
            continue
        out.append(ch.lower())
    return "".join(out)


_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def _tokens(normalized: str) -> list[str]:
    return [t for t in _TOKEN_SPLIT.split(normalized) if t]


class ScopeIsolationVerifier:
    def __init__(
        self,
        *,
        extra_banned_tokens: Iterable[str] = (),
        extra_banned_exact: Iterable[str] = (),
        extra_patterns: Iterable[str] = (),
    ) -> None:
        self._banned_tokens = set(BANNED_TOKENS) | {t.lower() for t in extra_banned_tokens}
        self._banned_exact = set(BANNED_EXACT) | {t.lower() for t in extra_banned_exact}
        # Caller-supplied extra regex patterns operate on the normalized string.
        self._extra_patterns = [re.compile(p, re.IGNORECASE) for p in extra_patterns]

    def register_blocked(self, pattern: str) -> None:
        """Append an additional regex pattern (operates on the normalized form)."""
        self._extra_patterns.append(re.compile(pattern, re.IGNORECASE))

    def register_token(self, token: str) -> None:
        self._banned_tokens.add(token.lower())

    def assert_isolated(
        self,
        target: str,
        artifacts_ref: str | None = None,
    ) -> None:
        """Raise ScopeIsolationViolation if `target` resolves to prod.

        Both `target` and `artifacts_ref` are checked — the latter because
        manifests / config refs frequently encode the environment.
        """
        candidates: list[tuple[str, str]] = [("target", target)]
        if artifacts_ref:
            candidates.append(("artifacts_ref", artifacts_ref))

        for label, value in candidates:
            if not isinstance(value, str):
                raise ScopeIsolationViolation(
                    f"{label} must be a string (got {type(value).__name__})"
                )
            normalized = _normalize(value)
            if normalized in self._banned_exact:
                raise ScopeIsolationViolation(
                    f"{label} {value!r} matches a banned exact target "
                    f"({normalized!r})"
                )
            for token in _tokens(normalized):
                if token in self._banned_tokens:
                    raise ScopeIsolationViolation(
                        f"{label} {value!r} contains banned token {token!r}"
                    )
                # Also flag tokens that START with a banned word followed by
                # digits or hyphens, since `prod1` / `prod-eu` are still prod.
                for banned in self._banned_tokens:
                    if token != banned and token.startswith(banned) and (
                        token[len(banned):].isdigit()
                        or token[len(banned):].startswith("-")
                    ):
                        raise ScopeIsolationViolation(
                            f"{label} {value!r} token {token!r} matches "
                            f"prod-prefix {banned!r}"
                        )
            for pat in self._extra_patterns:
                if pat.search(normalized):
                    raise ScopeIsolationViolation(
                        f"{label} {value!r} matches extra pattern "
                        f"{pat.pattern!r}"
                    )
