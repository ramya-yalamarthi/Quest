"""
State machine definitions (WBS task O-04).

A ticket moves linearly through the pipeline states and can drop to BLOCKED on
error, timeout, or an engineer rejection.

    INIT -> ROUTING -> DIAGNOSIS -> RECOMMENDATION -> DONE
                         (any) ----------------------> BLOCKED
"""

from enum import Enum

from app.orchestrator.events import EventType


class TicketState(str, Enum):
    INIT = "INIT"
    ROUTING = "ROUTING"
    DIAGNOSIS = "DIAGNOSIS"
    RECOMMENDATION = "RECOMMENDATION"
    DONE = "DONE"
    BLOCKED = "BLOCKED"


# Which agents run for each event type, in order (the core routing rule, O-01).
PIPELINES: dict[EventType, list[str]] = {
    EventType.CREATE: ["routing"],
    EventType.TRANSFER: ["routing", "diagnosis"],
    EventType.REACTIVATE: ["routing", "diagnosis", "recommendation"],
}

# The state a ticket is in while a given agent is running.
AGENT_STATE: dict[str, str] = {
    "routing": TicketState.ROUTING.value,
    "diagnosis": TicketState.DIAGNOSIS.value,
    "recommendation": TicketState.RECOMMENDATION.value,
}
