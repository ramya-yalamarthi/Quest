"""
Tests for the supervisor -- pure logic, no DB/Redis (uses in-memory store + fakes).

Run either way:
    cd backend
    python -m app.orchestrator.test_orchestrator      # plain asserts, prints OK
    pytest app/orchestrator/test_orchestrator.py       # if pytest installed
"""

from app.orchestrator.orchestrator import Orchestrator
from app.orchestrator.events import EventType, classify_event
from app.orchestrator.states import TicketState


def _fresh() -> Orchestrator:
    return Orchestrator()


def test_classify_explicit_and_inferred():
    assert classify_event({"event_type": "transfer"}) == EventType.TRANSFER
    assert classify_event({"reactivation_count": 3}) == EventType.REACTIVATE
    assert classify_event({"previous_team": "Networking"}) == EventType.TRANSFER
    assert classify_event({}) == EventType.CREATE


def test_create_runs_routing_only():
    orch = _fresh()
    rec = orch.handle_event({"event_id": "a", "event_type": "create", "ticket_id": "t-create"})
    assert rec.pipeline == ["routing"]
    rec = orch.handle_decision("t-create", "accept")
    assert rec.state == TicketState.DONE.value


def test_reactivate_runs_all_three_agents_in_order():
    orch = _fresh()
    rec = orch.handle_event({"event_id": "b", "event_type": "reactivate",
                             "ticket_id": "t-react", "reactivation_count": 1})
    assert rec.pipeline == ["routing", "diagnosis", "recommendation"]
    assert rec.current_agent == "routing"
    rec = orch.handle_decision("t-react", "accept")
    assert rec.current_agent == "diagnosis"
    rec = orch.handle_decision("t-react", "accept")
    assert rec.current_agent == "recommendation"
    rec = orch.handle_decision("t-react", "accept")
    assert rec.state == TicketState.DONE.value
    assert len(rec.advisories) == 3


def test_duplicate_event_is_ignored():
    orch = _fresh()
    orch.handle_event({"event_id": "dup", "event_type": "create", "ticket_id": "t-dup"})
    before = len(orch.audit.events)
    orch.handle_event({"event_id": "dup", "event_type": "create", "ticket_id": "t-dup"})
    # The duplicate adds exactly one "ignored" audit note and runs no agent.
    notes = [e for e in orch.audit.events[before:] if "duplicate" in (e["note"] or "")]
    assert len(notes) == 1


def test_reject_blocks_and_flags_retraining():
    orch = _fresh()
    orch.handle_event({"event_id": "r", "event_type": "reactivate",
                       "ticket_id": "t-rej", "reactivation_count": 1})
    rec = orch.handle_decision("t-rej", "reject")
    assert rec.state == TicketState.BLOCKED.value
    assert "retraining" in rec.status_detail.lower()


def test_second_event_same_ticket_gets_fresh_event_context():
    # Regression: a later event on the same ticket must not reuse the
    # first event's cached context (event_type/payload must be current).
    orch = _fresh()
    orch.handle_event({"event_id": "c1", "event_type": "create", "ticket_id": "t-multi"})
    rec = orch.handle_event({"event_id": "c2", "event_type": "reactivate",
                             "ticket_id": "t-multi", "reactivation_count": 1})
    assert rec.context["event"]["type"] == "reactivate"
    assert rec.context["event"]["payload"].get("reactivation_count") == 1


def test_missing_ticket_id_raises():
    orch = _fresh()
    try:
        orch.handle_event({"event_type": "create"})
        assert False, "expected ValueError"
    except ValueError:
        pass


def _main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\nAll {len(tests)} tests passed.")


if __name__ == "__main__":
    _main()
