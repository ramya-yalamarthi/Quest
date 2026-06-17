"""
Orchestration / Supervisor Agent (Day 4).

The supervisor sits between the ICM ticket system and the specialist agents.
It does NOT diagnose or route-to-team itself -- it decides *which* agents run,
*in what order*, tracks each ticket through a state machine, and writes an
audit trail.

Public entry point:
    from app.orchestrator import Orchestrator

Maps to WBS tasks O-01 .. O-11. See README.md in this package.
"""

from app.orchestrator.orchestrator import Orchestrator, OrchestrationRecord
from app.orchestrator.events import EventType, classify_event
from app.orchestrator.states import TicketState

__all__ = [
    "Orchestrator",
    "OrchestrationRecord",
    "EventType",
    "classify_event",
    "TicketState",
]
