"""
The Supervisor / Orchestration Agent (WBS Day 4, tasks O-01 .. O-11).

Responsibilities (and nothing more):
  * O-03  classify the incoming event (create / transfer / reactivate)
  * O-11  ignore duplicate events; reject malformed ones
  * O-05  build & cache the context the agents need
  * O-01  decide which agents run, in what order
  * O-04  track each ticket through a state machine
  * O-09  handle the engineer's ACCEPT / REJECT between agents
  * O-06  write an audit record for every step

It does NOT route-to-team, diagnose, or recommend -- those are the sub-agents.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Optional

from app.orchestrator.agents import default_agents
from app.orchestrator.audit import AuditLogger
from app.orchestrator.events import classify_event
from app.orchestrator.mcp_client import MockMCPClient
from app.orchestrator.probe import ProbeScheduler
from app.orchestrator.states import AGENT_STATE, PIPELINES, TicketState
from app.orchestrator.store import get_state_store


@dataclass
class OrchestrationRecord:
    """The full state of one ticket moving through the pipeline."""
    ticket_id: str
    event_id: str
    event_type: str
    pipeline: list[str]
    current_index: int = -1               # -1 = not started; index into pipeline
    state: str = TicketState.INIT.value
    context: dict = field(default_factory=dict)
    advisories: list[dict] = field(default_factory=list)
    status_detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "OrchestrationRecord":
        return cls(**d)

    @property
    def current_agent(self) -> Optional[str]:
        if 0 <= self.current_index < len(self.pipeline):
            return self.pipeline[self.current_index]
        return None


class Orchestrator:
    def __init__(self, store=None, mcp=None, agents=None, audit=None,
                 probe=None, symptom_check=None) -> None:
        self.store = store or get_state_store()
        self.mcp = mcp or MockMCPClient()
        self.agents = agents or default_agents()
        self.audit = audit or AuditLogger()
        # R-08 health-check probe (optional wiring). Default symptom check
        # reports "resolved" so the probe is inert until a real ServiceNow check
        # is injected; the 15-min timer is overridable via PROBE_DELAY_SECONDS.
        self.probe = probe or ProbeScheduler(
            delay_seconds=float(os.getenv("PROBE_DELAY_SECONDS", "900"))
        )
        self.symptom_check = symptom_check or (lambda ticket_id: True)

    # -- entry point: a new ICM event arrives -----------------------------
    def handle_event(self, payload: dict) -> Optional[OrchestrationRecord]:
        ticket_id = payload.get("ticket_id")
        event_type = classify_event(payload)                     # O-03
        event_id = payload.get("event_id") or f"{ticket_id}:{event_type.value}"

        # O-11: reject malformed events -- no silent failures.
        if not ticket_id:
            self.audit.log("(unknown)", "supervisor", note="rejected: payload missing ticket_id")
            raise ValueError("payload missing required field 'ticket_id'")

        # O-11: duplicate-event guard (atomic with Redis SET NX).
        if not self.store.mark_event_seen(event_id):
            self.audit.log(ticket_id, "supervisor", note=f"duplicate event {event_id} ignored")
            existing = self.store.load_state(ticket_id)
            return OrchestrationRecord.from_dict(existing) if existing else None

        record = OrchestrationRecord(
            ticket_id=ticket_id,
            event_id=event_id,
            event_type=event_type.value,
            pipeline=list(PIPELINES[event_type]),                # O-01
        )
        record.context = self._build_context(record, payload)    # O-05
        self._save(record)
        self.audit.log(
            ticket_id, "supervisor",
            note=f"event={event_type.value} -> pipeline={record.pipeline}",
        )
        return self._advance(record)                             # run first agent

    # -- engineer responded to the posted advisory (O-09) -----------------
    def handle_decision(self, ticket_id: str, decision: str) -> OrchestrationRecord:
        raw = self.store.load_state(ticket_id)
        if not raw:
            raise KeyError(f"no orchestration state for ticket {ticket_id}")
        record = OrchestrationRecord.from_dict(raw)
        agent = record.current_agent or "supervisor"
        decision = decision.strip().lower()

        if decision == "accept":
            self.audit.log(ticket_id, agent, note="engineer ACCEPTED advisory", was_used=True)
            # R-08: accepting a recommendation arms a delayed health-check probe.
            if agent == "recommendation":
                self._schedule_probe(ticket_id)
            return self._advance(record)                         # next agent or DONE

        if decision == "reject":
            record.state = TicketState.BLOCKED.value
            record.status_detail = "Engineer rejected advisory; override logged, retraining flagged."
            self._save(record)
            self.audit.log(ticket_id, agent, note="engineer REJECTED advisory; retraining flagged",
                           was_used=False)
            return record

        raise ValueError("decision must be 'accept' or 'reject'")

    def get_state(self, ticket_id: str) -> Optional[OrchestrationRecord]:
        raw = self.store.load_state(ticket_id)
        return OrchestrationRecord.from_dict(raw) if raw else None

    # -- internals --------------------------------------------------------
    def _build_context(self, record: OrchestrationRecord, payload: dict) -> dict:
        """O-05: assemble the context the agents consume.

        Only the expensive, ticket-level lookups (ticket data + history) are
        cached -- keyed by ticket_id.  The *event* portion is always rebuilt
        from the current payload so a later event on the same ticket never
        sees a stale event_type/payload.
        """
        cached = self.store.get_cached_context(record.ticket_id)
        if cached is None:
            cached = {
                "ticket": self.mcp.ticket_context_fetch(record.ticket_id),
                "history": self.mcp.gold_layer_lookup(record.ticket_id),
            }
            self.store.cache_context(record.ticket_id, cached)
        return {**cached, "event": {"type": record.event_type, "payload": payload}}

    def _advance(self, record: OrchestrationRecord) -> OrchestrationRecord:
        """Move to the next agent in the pipeline, or finish (O-04)."""
        record.current_index += 1

        if record.current_index >= len(record.pipeline):
            record.state = TicketState.DONE.value
            self._save(record)
            self.audit.log(record.ticket_id, "supervisor", note="pipeline complete -> DONE")
            return record

        agent_name = record.pipeline[record.current_index]
        record.state = AGENT_STATE[agent_name]
        agent = self.agents[agent_name]

        output = agent.run(record.context)                       # call the sub-agent
        self.mcp.post_icm_comment(record.ticket_id, agent_name, output)  # O-08
        record.advisories.append({"agent": agent_name, "output": output})
        self._save(record)
        self.audit.log(                                          # O-06
            record.ticket_id, agent_name,
            input_data={"event_type": record.event_type},
            output_data=output,
            confidence=output.get("confidence"),
        )
        # State now waits at this agent for the engineer's ACCEPT/REJECT.
        return record

    def _save(self, record: OrchestrationRecord) -> None:
        self.store.save_state(record.ticket_id, record.to_dict())

    # -- R-08 health-check probe (fully optional; never breaks the pipeline) --
    def _schedule_probe(self, ticket_id: str) -> None:
        try:
            self.probe.schedule(ticket_id, lambda: self._run_probe(ticket_id))
        except Exception as exc:  # pragma: no cover - belt and braces
            self.audit.log(ticket_id, "recommendation", note=f"probe: scheduling failed ({exc})")

    def _run_probe(self, ticket_id: str) -> None:
        """Fired ~15 min after ACCEPT: if symptoms persist, re-surface the stored
        recommendation advisory and arm at most one follow-up (capped at 2)."""
        try:
            resolved = self.symptom_check(ticket_id)
        except Exception as exc:
            self.audit.log(ticket_id, "recommendation", note=f"probe: symptom_check failed ({exc})")
            return

        if resolved:
            self.audit.log(ticket_id, "recommendation", note="probe: symptoms resolved")
            return

        try:
            raw = self.store.load_state(ticket_id)
            if raw:
                record = OrchestrationRecord.from_dict(raw)
                last = next((a for a in reversed(record.advisories)
                             if a.get("agent") == "recommendation"), None)
                if last is not None:
                    self.mcp.post_icm_comment(ticket_id, "recommendation", last["output"])
        except Exception as exc:
            self.audit.log(ticket_id, "recommendation", note=f"probe: re-fire failed ({exc})")
            return

        self.audit.log(ticket_id, "recommendation",
                       note="probe: symptoms persist, advisory re-fired", was_used=False)
        self._schedule_probe(ticket_id)  # one follow-up; ProbeScheduler caps total
