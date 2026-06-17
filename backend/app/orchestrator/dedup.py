"""
In-process de-duplication guard so a Case is processed exactly once, even when
the webhook, Power Automate retries, and the background poller all fire for the
same new Case at the same time (they share this process on Render).

`case_has_note` alone can't prevent this: all the racers check "does a note
exist?" within the same ~20s processing window -- before any of them has posted
-- so they all see "no note yet" and all post. This claim guard closes that
window: the first caller claims the case, the rest skip immediately.
"""

from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_claims: dict[str, float] = {}
_DEFAULT_TTL = 600.0          # remember a claim for 10 min (well past one run)


def _norm(case_id: str) -> str:
    """Normalise a Case GUID so the same case always maps to the same claim key.
    The webhook gets Dataverse's LOWERCASE id; the pop-up gets the form's
    UPPERCASE/braced id ({65FA...}). Without this they'd be different keys and
    both would process the case -> duplicate note."""
    return (case_id or "").strip().strip("{}").lower()


def claim(case_id: str, ttl: float = _DEFAULT_TTL) -> bool:
    """Atomically claim a Case for processing. Returns True if THIS caller got
    the claim, False if it's already claimed (someone else is handling it)."""
    case_id = _norm(case_id)
    if not case_id:
        return True
    now = time.monotonic()
    with _lock:
        for k in [k for k, t in _claims.items() if now - t > ttl]:
            _claims.pop(k, None)                       # purge expired claims
        if case_id in _claims:
            return False
        _claims[case_id] = now
        return True


def release(case_id: str) -> None:
    """Release a claim so the Case can be retried (call on processing failure)."""
    case_id = _norm(case_id)
    if not case_id:
        return
    with _lock:
        _claims.pop(case_id, None)
