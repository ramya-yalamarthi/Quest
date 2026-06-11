"""
D365 poller (Approach #2 automation).

Watches Dynamics for newly created Cases and runs the pipeline on each, writing
the recommendation Note back -- no human trigger. This is the "create a Case ->
note appears on its own" piece.

Design:
  * Baseline at startup = the newest existing Case's created_on, so we DON'T
    back-process the whole corpus -- only Cases created after the poller starts.
  * Idempotent: skip any Case that already has an "AI Support Recommendation"
    note (survives restarts / overlapping polls).
  * Stateless and network-isolated for tests: poll_once takes the client +
    `since` and an optional process_fn, so it can be driven with fakes.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from app.orchestrator.d365_runner import process_case, NOTE_SUBJECT


def poll_once(
    client,
    since: str,
    corpus_top: int = 100,
    post: bool = True,
    process_fn: Optional[Callable] = None,
) -> tuple:
    """Process Cases created after `since` that have no AI note yet.

    Returns (processed_ticket_numbers, new_since). `new_since` is the newest
    created_on seen, to carry into the next poll.
    """
    cases = client.list_cases(top=corpus_top)
    if not cases:
        return [], since
    corpus = cases
    new_since = cases[0].get("created_on") or since
    proc = process_fn or (lambda case, corp: process_case(case, corp, org_base=client.cfg["base"]))

    processed = []
    for case in cases:
        created = case.get("created_on") or ""
        if since and created <= since:
            continue                                   # not new
        if client.case_has_note(case.get("id"), NOTE_SUBJECT):
            continue                                   # already handled
        try:
            _, note = proc(case, corpus)
            if post:
                client.create_case_note(case.get("id"), NOTE_SUBJECT, note)
            processed.append(case.get("ticket_number"))
        except Exception as exc:                       # one bad case must not stop the poll
            print(f"[poller] failed on {case.get('ticket_number')}: {exc}")
    return processed, new_since


def _seed_since(client, scan: int = 50) -> str:
    """Restart-safe watermark: resume just after the newest Case that already
    has an AI note (so we never back-process the old corpus, and we DO pick up
    anything created while the poller was down). Falls back to the newest Case."""
    cases = client.list_cases(top=scan)
    if not cases:
        return ""
    for c in cases:                                    # newest first
        if client.case_has_note(c.get("id"), NOTE_SUBJECT):
            return c.get("created_on") or ""
    return cases[0].get("created_on") or ""


def poll_loop(client, interval: int = 120, log: Callable = print) -> None:
    """Run forever, resiliently: every `interval` seconds, process new Cases.

    Nothing in here is allowed to kill the thread -- a bad credential or a
    transient error is logged each cycle and retried, so the Render logs always
    show what's happening (heartbeat + errors)."""
    log(f"[poller] starting (interval {interval}s)...")
    since = None
    while True:
        try:
            if since is None:                          # seed once D365 is reachable
                since = _seed_since(client)
                log(f"[poller] watching for Cases newer than {since or '(none)'}")
            processed, since = poll_once(client, since)
            log(f"[poller] cycle ok; {len(processed)} processed"
                + (": " + ", ".join(processed) if processed else ""))
        except Exception as exc:
            log(f"[poller] cycle error ({type(exc).__name__}): {exc}  "
                f"-- check AZURE_*/EMBEDDING_* env values; retrying.")
            since = None                               # re-seed next cycle
        time.sleep(interval)
