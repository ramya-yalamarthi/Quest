"""
Tests for the supervisor -- pure logic, no DB/Redis (uses in-memory store + fakes).

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
    RecommendationAgent,
    recommendation_to_resolution_payload,
)
from app.orchestrator.trusted_sources import is_trusted
from app.orchestrator.probe import ProbeScheduler
from app.orchestrator.similarity import rank_similar, case_text


def _fresh() -> Orchestrator:
    return Orchestrator()


# --- Recommendation Agent (UC3) test helpers --------------------------------

def _ctx(prior=None, title="Production SQL Server unresponsive",
         desc="Applications return 'connection timeout expired'."):
    ctx = {"ticket": {}, "event": {"type": "reactivate",
            "payload": {"ticket_id": "t-rec", "title": title, "description": desc}}}
    if prior is not None:
        ctx["prior_resolution"] = prior
    return ctx


def _full_llm_result(rct="db_connection_exhaustion", cm=False):
    return {
        "reference": "INC0010724",
        "root_cause": "Connection pool exhausted under load.",
        "root_cause_type": rct,
        "delta": {
            "what_changed": "Peak load higher than during the last incident.",
            "prior_fix_summary": "Restarted the SQL service to clear sessions.",
            "prior_fix_gap": "Restart cleared sessions but the pool limit was never raised.",
            "original_fix_held": False,
            "recurrence_pattern": "weekly under peak load",
            "delta_severity": "high",
        },
        "immediate_action": {"summary": "Recycle the app connection pool",
                             "steps": ["Restart the app pool"], "eta_minutes": 25},
        "durable_fix": {"summary": "Raise pool size and add leak detection",
                        "steps": ["Tune max pool size"], "eta_hours": 5,
                        "requires_change_mgmt": cm, "cm_justification": ""},
        "reasoning": "Symptoms match database connection exhaustion.",
        "confidence": 0.7,
    }


class _patch_llm:
    """Temporarily replace agents_mod.chat_json (and optionally get_prevention)."""
    def __init__(self, result, prevention=None):
        self._result = result
        self._prevention = prevention

    def __enter__(self):
        self._orig_chat = agents_mod.chat_json
        agents_mod.chat_json = lambda system, user, **kw: self._result
        if self._prevention is not None:
            self._orig_prev = agents_mod.get_prevention
            agents_mod.get_prevention = lambda rct: self._prevention
        return self

    def __exit__(self, *exc):
        agents_mod.chat_json = self._orig_chat
        if self._prevention is not None:
            agents_mod.get_prevention = self._orig_prev
        return False


def test_classify_explicit_and_inferred():
    assert classify_event({"event_type": "transfer"}) == EventType.TRANSFER
    assert classify_event({"reactivation_count": 3}) == EventType.REACTIVATE
    assert classify_event({"previous_team": "Networking"}) == EventType.TRANSFER
    assert classify_event({}) == EventType.CREATE


def test_create_runs_routing_then_diagnosis():
    orch = _fresh()
    rec = orch.handle_event({"event_id": "a", "event_type": "create", "ticket_id": "t-create"})
    assert rec.pipeline == ["routing", "diagnosis"]
    rec = orch.handle_decision("t-create", "accept")   # routing -> diagnosis
    assert rec.current_agent == "diagnosis"
    rec = orch.handle_decision("t-create", "accept")   # diagnosis -> DONE
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


def test_recommendation_output_has_full_shape():
    with _patch_llm(_full_llm_result()):
        out = RecommendationAgent().run(_ctx(prior={"resolution_text": "Restarted SQL.",
                                                    "root_cause": "pool exhausted"}))
    # delta incl. the core prior_fix_gap field
    assert out["delta"]["prior_fix_gap"]
    # both tracks
    assert out["immediate_action"]["eta_minutes"] == 25
    assert out["durable_fix"]["eta_hours"] == 5
    assert "requires_change_mgmt" in out["durable_fix"]            # CM flag present
    # prevention + links + resolution fields + confidence
    assert out["prevention"]["root_cause_type"] == "db_connection_exhaustion"
    assert out["prevention"]["actions"] and out["prevention"]["monitoring_rule"]
    assert isinstance(out["trusted_links"], list) and out["trusted_links"]
    assert out["resolution_text"] and out["root_cause"] and out["reasoning"]
    assert isinstance(out["outcome"], list)
    assert 0.0 <= out["confidence"] <= 1.0
    assert out["reference"] == "INC0010724" and out["reference_link"]


def test_recommendation_prior_present_vs_absent():
    # absent -> graceful "no prior resolution" delta (fallback path, LLM off)
    with _patch_llm(None):
        absent = RecommendationAgent().run(_ctx(prior=None))
    assert "no prior resolution" in absent["delta"]["prior_fix_gap"].lower()
    # present -> prior summary reflected in the delta
    with _patch_llm(None):
        present = RecommendationAgent().run(
            _ctx(prior={"resolution_text": "Bounced the service", "root_cause": "stale sessions"}))
    assert "bounced the service" in present["delta"]["prior_fix_summary"].lower()


def test_recommendation_llm_unavailable_fallback_no_crash():
    with _patch_llm(None):
        out = RecommendationAgent().run(_ctx())
    # full advisory shape even with no LLM
    for key in ("delta", "immediate_action", "durable_fix", "prevention",
                "trusted_links", "resolution_text", "confidence"):
        assert key in out


def test_recommendation_unknown_root_cause_type_falls_back_to_config_drift():
    with _patch_llm(_full_llm_result(rct="totally_made_up_key")):
        out = RecommendationAgent().run(_ctx())
    assert out["prevention"]["root_cause_type"] == "config_drift"
    # config_drift is a CM-required type -> backstop forces the flag True
    assert out["durable_fix"]["requires_change_mgmt"] is True


def test_recommendation_cm_backstop():
    # high-impact type with the LLM saying False -> forced True
    with _patch_llm(_full_llm_result(rct="db_storage_full", cm=False)):
        out = RecommendationAgent().run(_ctx())
    assert out["durable_fix"]["requires_change_mgmt"] is True
    # non-CM type stays False
    with _patch_llm(_full_llm_result(rct="hardware_thermal", cm=False)):
        out2 = RecommendationAgent().run(_ctx())
    assert out2["durable_fix"]["requires_change_mgmt"] is False


def test_recommendation_untrusted_links_dropped():
    tampered = {
        "prevention_actions": ["do x"], "monitoring_rule": "watch y",
        "trusted_links": [
            {"title": "good", "url": "https://learn.microsoft.com/a", "source": "Microsoft Learn"},
            {"title": "bad", "url": "http://evil.example.com/x", "source": "spoof"},
        ],
    }
    with _patch_llm(_full_llm_result(), prevention=tampered):
        out = RecommendationAgent().run(_ctx())
    urls = [l["url"] for l in out["trusted_links"]]
    assert "https://learn.microsoft.com/a" in urls
    assert all(is_trusted(u) for u in urls)            # untrusted one dropped
    assert "http://evil.example.com/x" not in urls


def test_recommendation_feedback_aware_confidence():
    base = 0.6
    likes = RecommendationAgent(feedback_stats=lambda rct: (3, 0))
    dislikes = RecommendationAgent(feedback_stats=lambda rct: (0, 3))
    few = RecommendationAgent(feedback_stats=lambda rct: (1, 1))
    assert abs(likes._adjust_confidence(base, "config_drift") - 0.72) < 1e-9      # 3/0 raises
    assert abs(dislikes._adjust_confidence(base, "config_drift") - 0.48) < 1e-9   # 0/3 lowers
    assert abs(few._adjust_confidence(base, "config_drift") - base) < 1e-9        # <3 unchanged


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


def test_recommendation_surfaces_similar_cases():
    ctx = _ctx()
    ctx["similar"] = [
        {"ticket_number": "CAS-01005", "title": "FW: OCourt efiling down",
         "description": "efiling unavailable", "score": 0.744},
        {"ticket_number": "CAS-01019", "title": "OCourt Issue",
         "description": "ocourt error", "score": 0.539},
    ]
    with _patch_llm(_full_llm_result()):
        out = RecommendationAgent().run(ctx)
    assert out.get("similar_cases")
    assert out["similar_cases"][0]["ticket_number"] == "CAS-01005"
    assert out["similar_cases"][0]["score"] == 0.744


def test_recommendation_to_resolution_payload_serializes_tracks():
    with _patch_llm(_full_llm_result()):
        out = RecommendationAgent().run(_ctx())
    payload = recommendation_to_resolution_payload(out, ticket_id="t-rec")
    tracks = [s["track"] for s in payload["recommendedsteps"]]
    assert tracks == ["immediate", "durable", "prevention"]
    assert payload["ticket_id"] == "t-rec"
    assert payload["resolution_text"] == out["resolution_text"]


# --- R-08 health-check probe -----------------------------------------------

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
    orch.handle_decision("t-probe", "accept")        # routing -> diagnosis
    orch.handle_decision("t-probe", "accept")        # diagnosis -> recommendation
    rec = orch.handle_decision("t-probe", "accept")  # recommendation accept -> probe + DONE
    return orch, rec


def test_probe_persists_refires_and_caps():
    orch, rec = _drive_to_recommendation_accept(symptom_check=lambda tid: False)
    assert rec.state == TicketState.DONE.value                 # pipeline still completes
    persist = [e for e in orch.audit.events if "symptoms persist" in (e["note"] or "")]
    assert len(persist) == 2                                   # capped at 2 total probes


def test_probe_resolved_stops():
    orch, rec = _drive_to_recommendation_accept(symptom_check=lambda tid: True)
    resolved = [e for e in orch.audit.events if "symptoms resolved" in (e["note"] or "")]
    persist = [e for e in orch.audit.events if "symptoms persist" in (e["note"] or "")]
    assert len(resolved) == 1 and len(persist) == 0


def test_probe_failure_never_breaks_pipeline():
    def boom(tid):
        raise RuntimeError("servicenow down")
    orch, rec = _drive_to_recommendation_accept(symptom_check=boom)
    assert rec.state == TicketState.DONE.value                 # never breaks the pipeline
    failed = [e for e in orch.audit.events if "symptom_check failed" in (e["note"] or "")]
    assert len(failed) == 1


def test_probe_not_armed_for_non_recommendation_accept():
    orch = Orchestrator(probe=_instant_probe(), symptom_check=lambda tid: False)
    orch.handle_event({"event_id": "pc", "event_type": "create", "ticket_id": "t-noprobe"})
    orch.handle_decision("t-noprobe", "accept")      # routing -> diagnosis
    orch.handle_decision("t-noprobe", "accept")      # diagnosis -> DONE (no recommendation)
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
        {"id": "q", "title": "self", "description": "coffee"},        # same id -> excluded
        {"id": "a", "title": "Network down", "description": "network"},
        {"id": "b", "title": "Coffeemaker won't heat", "description": "coffee"},
    ]
    res = rank_similar(query, corpus, top_k=5, embed_fn=_fake_embed)
    ids = [r["id"] for r in res]
    assert "q" not in ids                 # excludes the query itself
    assert ids[0] == "b"                  # most similar first
    assert res[0]["score"] > 0.99


def test_similarity_empty_when_no_embeddings():
    res = rank_similar({"id": "q", "title": "x", "description": "y"},
                       [{"id": "a", "title": "a", "description": "b"}],
                       embed_fn=lambda texts: None)
    assert res == []


def test_similarity_min_score_filters():
    query = {"id": "q", "title": "coffee", "description": "coffee"}
    corpus = [{"id": "a", "title": "network", "description": "network"}]  # orthogonal -> 0.0
    assert rank_similar(query, corpus, min_score=0.5, embed_fn=_fake_embed) == []


def test_case_text_builds_title_and_description():
    t = case_text({"title": "Hello", "description": "World"})
    assert "Title: Hello" in t and "World" in t


def test_d365_runner_format_and_process():
    from app.orchestrator.d365_runner import process_case
    case = {"id": "new", "title": "Coffee machine not heating", "description": "coffee"}
    corpus = [
        {"id": "b", "ticket_number": "CAS-1", "title": "Coffeemaker won't heat", "description": "coffee"},
        {"id": "a", "ticket_number": "CAS-2", "title": "Network down", "description": "network"},
    ]
    with _patch_llm(_full_llm_result()):
        advisory, note = process_case(case, corpus, embed_fn=_fake_embed)
    assert "AI SUPPORT RECOMMENDATION" in note
    assert "IMMEDIATE" in note and "DURABLE" in note
    assert advisory.get("similar_cases")          # grounded in real matches
    assert "CAS-1" in note                         # top match cited in the note


def _main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\nAll {len(tests)} tests passed.")


if __name__ == "__main__":
    _main()
