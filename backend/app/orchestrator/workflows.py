"""Shared keyword -> workflow lookup, used both for the ticket-level
"suggested workflow" (d365_runner.py) and per-KB-article "workflow available"
tagging (app/agents/kb.py) -- one definition, two consumers.

These are steps for a HUMAN to run, never auto-executed; there's no API or
Power Automate wiring behind any of this.
"""
from __future__ import annotations

from typing import Optional

# Category/keyword -> a workflow that COULD be triggered (capacity/quota
# changes, scale-up) -- always shown as a SUGGESTION, never auto-run. Keep
# this conservative: only suggest when the signal is clear, since a wrong
# suggestion erodes trust faster than no suggestion.
WORKFLOW_SUGGESTIONS = (
    (("quota", "capacity", "instance types", "pricing"), {
        "title": "Increase NodePool/instance-type quota or capacity allocation",
        "steps": [
            "Check current quota/limits for the affected instance type (cloud console or NodePool spec).",
            "Raise the NodePool's instance-type/capacity limit to cover the shortfall.",
            "Apply the updated NodePool configuration.",
            "Confirm Karpenter provisions new nodes and the pending pods schedule.",
        ],
    }),
    (("autoscaling", "scale-up", "scale down", "scaling"), {
        "title": "Review/trigger an autoscaling policy adjustment",
        "steps": [
            "Check the autoscaler logs for recent scale-up/scale-down decisions.",
            "Review the policy thresholds (min/max nodes, scale-down delay).",
            "Adjust the thresholds if scaling is too conservative for current load.",
            "Trigger a manual scale-up if pods are pending on insufficient nodes.",
        ],
    }),
    (("pending", "provisioning", "nodepool", "scheduling"), {
        "title": "Run a NodePool provisioning health-check",
        "steps": [
            "Verify the Karpenter controller is running and healthy.",
            "Check the NodePool/EC2NodeClass status for errors.",
            "Confirm cloud-provider service quotas aren't blocking provisioning.",
            "Re-trigger provisioning once the blocker is cleared and confirm pods schedule.",
        ],
    }),
)


def find_workflow(*texts: str) -> Optional[dict]:
    """First workflow whose keywords appear in any of `texts`. None (no
    filler) if nothing clearly points to one."""
    haystack = " ".join(t or "" for t in texts).lower()
    for keywords, workflow in WORKFLOW_SUGGESTIONS:
        if any(k in haystack for k in keywords):
            return workflow
    return None
