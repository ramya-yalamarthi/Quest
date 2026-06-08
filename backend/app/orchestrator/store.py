"""
State store (WBS tasks O-04 state persistence, O-05 context cache, O-11 dedupe).

Pluggable storage behind one small interface:

  * InMemoryStateStore  -> default; zero setup; great for the POC demo.
  * RedisStateStore     -> activated by setting the REDIS_URL env var.

Both back three things the supervisor needs:
  1. ticket pipeline state   (which agent it's on)
  2. event dedupe            (ignore duplicate webhook deliveries)
  3. context cache           (build context once, reuse for a few minutes)

Swap is a config switch -- the orchestrator code never changes.
"""

from __future__ import annotations

import json
import os
from typing import Optional, Protocol

CONTEXT_TTL_SECONDS = 300  # cache assembled ticket context for 5 minutes


class StateStore(Protocol):
    def save_state(self, ticket_id: str, record: dict) -> None: ...
    def load_state(self, ticket_id: str) -> Optional[dict]: ...
    def mark_event_seen(self, event_id: str) -> bool:
        """Return True if this event_id is NEW (first time), False if duplicate."""
        ...
    def cache_context(self, ticket_id: str, context: dict, ttl: int = CONTEXT_TTL_SECONDS) -> None: ...
    def get_cached_context(self, ticket_id: str) -> Optional[dict]: ...


class InMemoryStateStore:
    """Simple process-local store. State is lost on restart -- fine for the POC.

    Behaves like Redis closely enough that swapping to RedisStateStore needs no
    orchestrator changes.  (Context TTL is not enforced in memory; not needed
    for the demo.)
    """

    def __init__(self) -> None:
        self._state: dict[str, dict] = {}
        self._seen_events: set[str] = set()
        self._context: dict[str, dict] = {}

    def save_state(self, ticket_id: str, record: dict) -> None:
        self._state[ticket_id] = json.loads(json.dumps(record))  # deep copy

    def load_state(self, ticket_id: str) -> Optional[dict]:
        rec = self._state.get(ticket_id)
        return json.loads(json.dumps(rec)) if rec is not None else None

    def mark_event_seen(self, event_id: str) -> bool:
        if event_id in self._seen_events:
            return False
        self._seen_events.add(event_id)
        return True

    def cache_context(self, ticket_id: str, context: dict, ttl: int = CONTEXT_TTL_SECONDS) -> None:
        self._context[ticket_id] = json.loads(json.dumps(context))

    def get_cached_context(self, ticket_id: str) -> Optional[dict]:
        ctx = self._context.get(ticket_id)
        return json.loads(json.dumps(ctx)) if ctx is not None else None


class RedisStateStore:
    """Production store backed by Redis.

    * state   -> key  orch:state:{ticket_id}   (JSON string)
    * dedupe  -> key  orch:event:{event_id}     (SET ... NX  == atomic first-seen)
    * context -> key  orch:ctx:{ticket_id}      (JSON string with TTL)
    """

    def __init__(self, redis_url: str, dedupe_ttl: int = 24 * 3600) -> None:
        import redis  # imported lazily so the package works without redis installed

        self._r = redis.Redis.from_url(redis_url, decode_responses=True)
        self._dedupe_ttl = dedupe_ttl

    def save_state(self, ticket_id: str, record: dict) -> None:
        self._r.set(f"orch:state:{ticket_id}", json.dumps(record))

    def load_state(self, ticket_id: str) -> Optional[dict]:
        raw = self._r.get(f"orch:state:{ticket_id}")
        return json.loads(raw) if raw else None

    def mark_event_seen(self, event_id: str) -> bool:
        # SET key val NX EX ttl -> returns True only if the key did not exist.
        created = self._r.set(f"orch:event:{event_id}", "1", nx=True, ex=self._dedupe_ttl)
        return bool(created)

    def cache_context(self, ticket_id: str, context: dict, ttl: int = CONTEXT_TTL_SECONDS) -> None:
        self._r.set(f"orch:ctx:{ticket_id}", json.dumps(context), ex=ttl)

    def get_cached_context(self, ticket_id: str) -> Optional[dict]:
        raw = self._r.get(f"orch:ctx:{ticket_id}")
        return json.loads(raw) if raw else None


def get_state_store() -> StateStore:
    """Pick the store from the environment.

    Set REDIS_URL (e.g. redis://localhost:6379/0) to use Redis; otherwise the
    in-memory store is used so everything runs with zero setup.
    """
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            return RedisStateStore(redis_url)
        except Exception as exc:  # pragma: no cover - fall back if redis missing/down
            print(f"[orchestrator] REDIS_URL set but Redis unavailable ({exc}); "
                  f"falling back to in-memory store.")
    return InMemoryStateStore()
