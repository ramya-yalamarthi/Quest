"""
Runnable end-to-end demo of the supervisor.

Runs standalone -- no live Postgres or Redis connection required.  It uses the
in-memory state store and the mock MCP client + stub agents, so you can see the
full orchestration flow with zero setup:

    cd backend
    python -m app.orchestrator.demo

(The real wiring -- Redis state + Postgres ai_audit_log + real agents -- is the
same code with REDIS_URL set and the db_sink / real agents passed in.)
"""

from app.orchestrator.orchestrator import Orchestrator
from app.orchestrator.states import TicketState


def _run_to_completion(orch: Orchestrator, payload: dict) -> None:
    print(f"\n=== EVENT: {payload.get('event_type')}  (ticket {payload['ticket_id']}) ===")
    record = orch.handle_event(payload)
    print(f"  classified -> pipeline {record.pipeline}")
    # Simulate the engineer accepting each advisory until the pipeline finishes.
    while record.state not in (TicketState.DONE.value, TicketState.BLOCKED.value):
        print(f"  state={record.state:<14} agent '{record.current_agent}' posted advisory -> ACCEPT")
        record = orch.handle_decision(record.ticket_id, "accept")
    print(f"  FINAL state = {record.state}")


def main() -> None:
    orch = Orchestrator()  # fakes everywhere; set REDIS_URL to use real Redis

    _run_to_completion(orch, {"event_id": "e1", "event_type": "create",
                              "ticket_id": "11111111-1111-1111-1111-111111111111", "priority": "P2"})
    _run_to_completion(orch, {"event_id": "e2", "event_type": "transfer",
                              "ticket_id": "22222222-2222-2222-2222-222222222222", "previous_team": "Networking"})
    _run_to_completion(orch, {"event_id": "e3", "event_type": "reactivate",
                              "ticket_id": "33333333-3333-3333-3333-333333333333", "reactivation_count": 2})

    print("\n=== O-11: duplicate event (same event_id 'e1') is ignored ===")
    orch.handle_event({"event_id": "e1", "event_type": "create",
                       "ticket_id": "11111111-1111-1111-1111-111111111111"})

    print("\n=== O-09: a REJECT blocks the pipeline + flags retraining ===")
    rec = orch.handle_event({"event_id": "e4", "event_type": "reactivate",
                             "ticket_id": "44444444-4444-4444-4444-444444444444", "reactivation_count": 1})
    rec = orch.handle_decision(rec.ticket_id, "reject")
    print(f"  ticket {rec.ticket_id} -> state={rec.state}: {rec.status_detail}")

    print(f"\n=== AUDIT TRAIL ({len(orch.audit.events)} events) ===")
    for e in orch.audit.events:
        line = e["note"] or (e.get("output_json") or {}).get("title", "")
        print(f"  {e['created_at'][11:19]}  {e['agent_name']:<14} {line}")


if __name__ == "__main__":
    main()
