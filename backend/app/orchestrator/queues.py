"""
D365 queue routing -- moves a Case into the matching native Dataverse queue
once the RoutingAgent has classified it, so the queue the engineer actually
sees in D365 reflects the same decision as the case note / assignment email.

The 9 k8s/Karpenter categories the RoutingAgent classifies into roll up into
3 broader queues (Software / Hardware / Network), matching the demo's queue
setup -- override the mapping or queue names via env if yours differ.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

_HARDWARE_TEAMS = {"Instance types / pricing"}
_NETWORK_TEAMS = {"Networking"}
# everything else (Provisioning/scheduling, Autoscaling/scaling,
# Consolidation/disruption, Metrics/observability, Termination/eviction,
# Config/API (EC2NodeClass), Docs, Other) -> Software

QUEUE_NAMES = {
    "Software": os.getenv("SOFTWARE_QUEUE_NAME", "Software Queue"),
    "Hardware": os.getenv("HARDWARE_QUEUE_NAME", "Hardware Queue"),
    "Network": os.getenv("NETWORK_QUEUE_NAME", "Network Queue"),
}


def domain_for_team(team: str) -> str:
    if team in _HARDWARE_TEAMS:
        return "Hardware"
    if team in _NETWORK_TEAMS:
        return "Network"
    return "Software"


def move_case_to_queue(client, case_id: str, team: str) -> bool:
    """Best-effort: move `case_id` into the D365 queue matching `team`'s
    domain. Returns True if the move succeeded, False on any failure (missing
    queue, API error) -- never raises, so a queue-routing problem can't break
    the case pipeline."""
    domain = domain_for_team(team)
    queue_name = QUEUE_NAMES[domain]
    try:
        queue_id = client.get_queue_id(queue_name)
        if not queue_id:
            log.warning("Queue '%s' not found in D365; skipping queue move", queue_name)
            return False
        client.set_case_queue(case_id, queue_id)
        return True
    except Exception:
        log.exception("Failed to move case %s to queue '%s'", case_id, queue_name)
        return False
