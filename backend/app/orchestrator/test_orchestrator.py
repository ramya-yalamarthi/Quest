"""
Tests for the supervisor + agents -- pure logic, no DB/Redis (in-memory + fakes).

Run either way:
    cd backend
    python -m app.orchestrator.test_orchestrator      # plain asserts, prints OK
    pytest app/orchestrator/test_orchestrator.py       # if pytest installed
"""

import app.orchestrator.agents as agents_mod
from app.orchestrator.orchestrator import Orchestrator
from app.orchestrator.events import EventType, classify_event
from app.orchestrator.states import TicketState
from app.orchestrator.agents import (
    RoutingAgent, DiagnosisAgent, RecommendationAgent,
    recommendation_to_resolution_payload,
)
from app.orchestrator.trusted_sources import is_trusted
from app.orchestrator.probe import ProbeScheduler
from app.orchestrator.similarity import rank_similar, case_text


def _fresh() -> Orchestrator:
    return Orchestrator()


# --- agent test helpers -----------------------------------------------------

def _ctx(title="nCourt payments failing at checkout",
         desc="Users cannot complete nCourt payments; error at checkout.",
         assigned_team="", similar=None):
    ctx = {"ticket": {}, "event": {"type": "reactivate", "payload": {
        "ticket_id": "t-rec", "title": title, "description": desc,
        "assigned_team": assigned_team}}}
    if similar is not None:
        ctx["similar"] = similar
    return ctx


def _llm_stub(cm=False, links=None, team="Payments"):
    """One stub covering keys for all three agents (chat_json is patched globally)."""
    return {
        "recommended_team": team,
        "root_cause": "nCourt payment gateway integration is failing.",
        "hot_fix": {"summary": "Restart the payment gateway connector.",
                    "steps": ["Restart the connector", "Run a test payment"]},
        "ultimate_fix": {"summary": "Add retry + monitoring to the gateway integration.",
                         "steps": ["Add retry logic", "Add an alert"],
                         "requires_change_mgmt": cm,
                         "cm_justification": "Integration change" if cm else ""},
        "reference_links": links if links is not None else
            [{"title": "Payment connectors", "url": "https://learn.microsoft.com/x", "source": "Microsoft Learn"}],
        "confidence": 0.7,
    }


class _patch_llm:
    """Temporarily replace agents_mod.chat_json with a canned result (or None)."""
    def __init__(self, result):
        self._result = result

    def __enter__(self):
        self._orig = agents_mod.chat_json
        agents_mod.chat_json = lambda system, user, **kw: self._result
        return self

    def __exit__(self, *exc):
        agents_mod.chat_json = self._orig
        return False


# --- orchestrator / supervisor ----------------------------------------------

def test_classify_explicit_and_inferred():
    assert classify_event({"event_type": "transfer"}) == EventType.TRANSFER
    assert classify_event({"reactivation_count": 3}) == EventType.REACTIVATE
    assert classify_event({"previous_team": "Networking"}) == EventType.TRANSFER
    assert classify_event({}) == EventType.CREATE


def test_create_runs_routing_then_diagnosis():
    orch = _fresh()
    rec = orch.handle_event({"event_id": "a", "event_type": "create", "ticket_id": "t-create"})
    assert rec.pipeline == ["routing", "diagnosis"]
    rec = orch.handle_decision("t-create", "accept")
    assert rec.current_agent == "diagnosis"
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


# --- Routing agent ----------------------------------------------------------

def test_routing_recommends_team_when_unassigned():
    with _patch_llm(_llm_stub(team="Payments")):
        out = RoutingAgent().run(_ctx())
    assert out["recommended_team"] == "Payments"
    assert out["assignment_correct"] is None          # no team on the case yet
    assert out["assigned_team"] == "Unassigned"


def test_routing_flags_wrong_team():
    with _patch_llm(_llm_stub(team="Payments")):
        out = RoutingAgent().run(_ctx(assigned_team="Infrastructure"))
    assert out["assignment_correct"] is False
    assert out["recommended_team"] == "Payments"


def test_routing_confirms_correct_team():
    with _patch_llm(_llm_stub(team="Payments")):
        out = RoutingAgent().run(_ctx(assigned_team="Payments"))
    assert out["assignment_correct"] is True


# --- Diagnosis agent --------------------------------------------------------

def test_diagnosis_returns_root_cause_only():
    with _patch_llm(_llm_stub()):
        out = DiagnosisAgent().run(_ctx())
    assert out["root_cause"]
    assert "reference" not in out and "reasoning" not in out   # dropped


def test_diagnosis_fallback_when_no_llm():
    with _patch_llm(None):
        out = DiagnosisAgent().run(_ctx())
    assert out["root_cause"]


# --- Recommendation agent ---------------------------------------------------

def test_recommendation_new_shape():
    with _patch_llm(_llm_stub()):
        out = RecommendationAgent().run(_ctx())
    assert out["hot_fix"]["summary"] and out["ultimate_fix"]["summary"]
    assert "requires_change_mgmt" in out["ultimate_fix"]
    assert isinstance(out["trusted_links"], list) and out["trusted_links"]
    assert 0.0 <= out["confidence"] <= 1.0
    for gone in ("prevention", "delta", "reference", "immediate_action", "durable_fix"):
        assert gone not in out                        # old fields removed


def test_recommendation_cm_flag_from_llm():
    with _patch_llm(_llm_stub(cm=True)):
        out = RecommendationAgent().run(_ctx())
    assert out["ultimate_fix"]["requires_change_mgmt"] is True
    with _patch_llm(_llm_stub(cm=False)):
        out2 = RecommendationAgent().run(_ctx())
    assert out2["ultimate_fix"]["requires_change_mgmt"] is False


def test_recommendation_untrusted_links_dropped():
    links = [
        {"title": "good", "url": "https://learn.microsoft.com/a", "source": "Microsoft Learn"},
        {"title": "reddit", "url": "https://www.reddit.com/r/x", "source": "Reddit"},
        {"title": "bad", "url": "http://evil.example.com/x", "source": "spoof"},
    ]
    with _patch_llm(_llm_stub(links=links)):
        out = RecommendationAgent().run(_ctx())
    urls = [l["url"] for l in out["trusted_links"]]
    assert "https://learn.microsoft.com/a" in urls
    assert "https://www.reddit.com/r/x" in urls        # reddit now trusted
    assert all(is_trusted(u) for u in urls)
    assert "http://evil.example.com/x" not in urls


def test_recommendation_fallback_when_no_llm():
    with _patch_llm(None):
        out = RecommendationAgent().run(_ctx())
    for key in ("hot_fix", "ultimate_fix", "trusted_links", "confidence"):
        assert key in out


def test_recommendation_invalid_feedback_verdict_rejected():
    from pydantic import ValidationError
    from app.schemas.feedback import FeedbackCreate
    import uuid
    FeedbackCreate(ticket_id=uuid.uuid4(), verdict="like")        # valid
    try:
        FeedbackCreate(ticket_id=uuid.uuid4(), verdict="meh")     # invalid -> 422 at the API
        assert False, "expected ValidationError"
    except ValidationError:
        pass


def test_recommendation_to_resolution_payload_serializes_tracks():
    with _patch_llm(_llm_stub()):
        out = RecommendationAgent().run(_ctx())
    payload = recommendation_to_resolution_payload(out, ticket_id="t-rec")
    tracks = [s["track"] for s in payload["recommendedsteps"]]
    assert tracks == ["hot_fix", "ultimate_fix"]
    assert payload["ticket_id"] == "t-rec"


# --- R-08 health-check probe ------------------------------------------------

class _InstantTimer:
    """Timer stub that fires synchronously on start() -- instant probe tests."""
    def __init__(self, interval, function):
        self._function = function
        self.daemon = False

    def start(self):
        self._function()


def _instant_probe():
    return ProbeScheduler(delay_seconds=0, timer_factory=_InstantTimer)


def _drive_to_recommendation_accept(symptom_check):
    orch = Orchestrator(probe=_instant_probe(), symptom_check=symptom_check)
    orch.handle_event({"event_id": "p", "event_type": "reactivate",
                       "ticket_id": "t-probe", "reactivation_count": 1})
    orch.handle_decision("t-probe", "accept")
    orch.handle_decision("t-probe", "accept")
    rec = orch.handle_decision("t-probe", "accept")
    return orch, rec


def test_probe_persists_refires_and_caps():
    orch, rec = _drive_to_recommendation_accept(symptom_check=lambda tid: False)
    assert rec.state == TicketState.DONE.value
    persist = [e for e in orch.audit.events if "symptoms persist" in (e["note"] or "")]
    assert len(persist) == 2


def test_probe_resolved_stops():
    orch, rec = _drive_to_recommendation_accept(symptom_check=lambda tid: True)
    resolved = [e for e in orch.audit.events if "symptoms resolved" in (e["note"] or "")]
    persist = [e for e in orch.audit.events if "symptoms persist" in (e["note"] or "")]
    assert len(resolved) == 1 and len(persist) == 0


def test_probe_failure_never_breaks_pipeline():
    def boom(tid):
        raise RuntimeError("d365 down")
    orch, rec = _drive_to_recommendation_accept(symptom_check=boom)
    assert rec.state == TicketState.DONE.value
    failed = [e for e in orch.audit.events if "symptom_check failed" in (e["note"] or "")]
    assert len(failed) == 1


def test_probe_not_armed_for_non_recommendation_accept():
    orch = Orchestrator(probe=_instant_probe(), symptom_check=lambda tid: False)
    orch.handle_event({"event_id": "pc", "event_type": "create", "ticket_id": "t-noprobe"})
    orch.handle_decision("t-noprobe", "accept")
    orch.handle_decision("t-noprobe", "accept")
    probe_notes = [e for e in orch.audit.events if "probe:" in (e["note"] or "")]
    assert probe_notes == []


# --- In-memory similarity (Approach #2) -------------------------------------

def _fake_embed(texts):
    """Deterministic stand-in for ada-002: 'coffee'->x, 'network'->y, else z."""
    out = []
    for t in texts:
        tl = t.lower()
        if "coffee" in tl:
            out.append([1.0, 0.0, 0.0])
        elif "network" in tl:
            out.append([0.0, 1.0, 0.0])
        else:
            out.append([0.0, 0.0, 1.0])
    return out


def test_similarity_ranks_and_excludes_self():
    query = {"id": "q", "title": "Coffee machine not heating", "description": "coffee"}
    corpus = [
        {"id": "q", "title": "self", "description": "coffee"},
        {"id": "a", "title": "Network down", "description": "network"},
        {"id": "b", "title": "Coffeemaker won't heat", "description": "coffee"},
    ]
    res = rank_similar(query, corpus, top_k=5, embed_fn=_fake_embed)
    ids = [r["id"] for r in res]
    assert "q" not in ids
    assert ids[0] == "b"
    assert res[0]["score"] > 0.99


def test_similarity_empty_when_no_embeddings():
    res = rank_similar({"id": "q", "title": "x", "description": "y"},
                       [{"id": "a", "title": "a", "description": "b"}],
                       embed_fn=lambda texts: None)
    assert res == []


def test_similarity_min_score_filters():
    query = {"id": "q", "title": "coffee", "description": "coffee"}
    corpus = [{"id": "a", "title": "network", "description": "network"}]
    assert rank_similar(query, corpus, min_score=0.5, embed_fn=_fake_embed) == []


def test_case_text_builds_title_and_description():
    t = case_text({"title": "Hello", "description": "World"})
    assert "Title: Hello" in t and "World" in t


# --- D365 runner: full pipeline -> one bound note ---------------------------

def test_d365_runner_full_pipeline_and_note():
    from app.orchestrator.d365_runner import process_case
    case = {"id": "new", "ticket_number": "CAS-NEW",
            "title": "Coffee machine not heating", "description": "coffee"}
    corpus = [
        {"id": "b", "ticket_number": "CAS-1", "title": "Coffeemaker won't heat", "description": "coffee"},
        {"id": "a", "ticket_number": "CAS-2", "title": "Network down", "description": "network"},
    ]
    with _patch_llm(_llm_stub()):
        advisory, note = process_case(case, corpus,
                                      org_base="https://org.crm.dynamics.com", embed_fn=_fake_embed)
    assert advisory.get("routing") and advisory.get("diagnosis") and advisory.get("recommendation")
    assert "AI SUPPORT ANALYSIS" in note
    assert "TEAM ASSIGNMENT" in note and "DIAGNOSIS" in note and "RECOMMENDATION" in note
    assert "Hot fix:" in note and "Ultimate fix:" in note
    assert "Reference links:" in note
    assert "CAS-1" in note and "% match" in note          # similar case + percentage
    assert "main.aspx" in note                            # clickable D365 link
    assert advisory["diagnosis"]["similar_incidents"]     # similarity is part of diagnosis
    assert "Confidence:" in note


# --- D365 poller (automation) -----------------------------------------------

class _FakeClient:
    cfg = {"base": "https://org.crm.dynamics.com"}

    def __init__(self, cases, noted=None):
        self._cases = cases
        self._noted = noted or set()
        self.posted = []

    def list_cases(self, top=100):
        return list(self._cases)[:top]

    def case_has_note(self, case_id, subject):
        return case_id in self._noted

    def create_case_note(self, case_id, subject, text):
        self.posted.append(case_id)
        return "ann-" + case_id


def _fake_proc(case, corpus):
    return {}, "NOTE for " + case["ticket_number"]


def test_poller_processes_only_new_cases():
    from app.orchestrator.d365_poller import poll_once
    cases = [
        {"id": "2", "ticket_number": "CAS-2", "title": "new", "description": "x",
         "created_on": "2026-06-11T10:00:00Z"},
        {"id": "1", "ticket_number": "CAS-1", "title": "old", "description": "x",
         "created_on": "2026-06-11T09:00:00Z"},
    ]
    client = _FakeClient(cases)
    processed, since = poll_once(client, since="2026-06-11T09:30:00Z", process_fn=_fake_proc)
    assert processed == ["CAS-2"]                 # only the newer case
    assert client.posted == ["2"]
    assert since == "2026-06-11T10:00:00Z"         # carry-forward watermark


def test_poller_is_idempotent_skips_noted():
    from app.orchestrator.d365_poller import poll_once
    cases = [{"id": "2", "ticket_number": "CAS-2", "title": "new", "description": "x",
              "created_on": "2026-06-11T10:00:00Z"}]
    client = _FakeClient(cases, noted={"2"})        # already has an AI note
    processed, _ = poll_once(client, since="2026-06-11T09:30:00Z", process_fn=_fake_proc)
    assert processed == [] and client.posted == []


def _main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\nAll {len(tests)} tests passed.")


if __name__ == "__main__":
    _main()
