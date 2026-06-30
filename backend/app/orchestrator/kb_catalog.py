"""
Static KB-article catalog for the popup's "Knowledge Base Recommendations"
section -- same approach as workflows.py's WORKFLOW_SUGGESTIONS: a small,
curated list matched by keyword overlap, no database required. (A DB-backed
version with embeddings + live success-rate tracking was tried and reverted --
see app/agents/kb.py -- because no Postgres is provisioned anywhere. This is
the no-infra replacement.)
"""
from __future__ import annotations

from app.orchestrator.workflows import find_workflow

# (title, url, summary, category, times_recommended, times_resolved, total_resolution_hours)
_RAW = [
    ("NodePool quota exhausted — capacity grace period and manual drain procedure",
     "https://karpenter.sh/docs/concepts/nodepools/",
     "When a NodePool's instance-type/capacity quota is exhausted, Karpenter can't "
     "provision new nodes and pods stay Pending. Raise the NodePool's limits, then "
     "cordon and manually drain any nodes stuck mid-termination before retrying.",
     "Instance types / pricing", 46, 39, 14.3),
    ("Pods stuck Pending — NodePool provisioning health-check",
     "https://karpenter.sh/docs/troubleshooting/",
     "Pods stuck in Pending usually trace back to the Karpenter controller, NodePool, "
     "or EC2NodeClass not provisioning. Checklist: controller health, NodePool/"
     "EC2NodeClass status, and cloud-provider quota limits blocking new nodes.",
     "Provisioning / scheduling", 58, 49, 12.1),
    ("Cluster autoscaler not scaling up under load — policy tuning guide",
     "https://kubernetes.io/docs/concepts/cluster-administration/cluster-autoscaling/",
     "If CPU/memory pressure is high but the autoscaler isn't adding nodes, check the "
     "scale-up policy thresholds and recent scale-up/scale-down decision logs before "
     "assuming a hard capacity limit.",
     "Autoscaling / scaling", 34, 27, 9.5),
    ("Node drain hangs and pods get force-deleted before EC2 terminates",
     "https://karpenter.sh/docs/concepts/disruption/",
     "NodeRepair / termination can set a grace period that ends up negative, bypassing "
     "normal pod shutdown sequencing and force-deleting pods before the underlying "
     "instance actually terminates -- causing overlapping old/new container lifecycles.",
     "Termination / eviction", 21, 12, 5.8),
    ("Karpenter consolidation/disruption budget not triggering scale-down",
     "https://karpenter.sh/docs/concepts/disruption/#disruption-budgets",
     "Idle nodes not consolidating despite disruption budgets allowing it is usually a "
     "drift/consolidation eligibility issue -- check do-not-disrupt annotations and "
     "consolidateAfter timing on the NodePool.",
     "Consolidation / disruption", 19, 11, 6.4),
    ("EC2NodeClass misconfiguration — subnet, AMI, and security group errors",
     "https://karpenter.sh/docs/concepts/nodeclasses/",
     "EC2NodeClass stuck unreconciled most often traces to a missing subnet, an AMI "
     "selector matching nothing, or a security group reference that no longer exists.",
     "Config / API (EC2NodeClass)", 15, 9, 4.2),
    ("Karpenter controller metrics and observability gaps",
     "https://karpenter.sh/docs/reference/metrics/",
     "When cost/utilization metrics look wrong (negative values, missing series), check "
     "the controller logs first -- most reporting bugs trace to a reconciler error, not "
     "an actual infrastructure problem.",
     "Metrics / observability", 12, 7, 3.9),
    ("Pod networking / DNS connectivity issues on newly provisioned nodes",
     "https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/",
     "New nodes failing DNS resolution or VPC connectivity is usually a security-group "
     "or subnet route table gap introduced by a NodePool/EC2NodeClass change, not a "
     "cluster DNS service issue.",
     "Networking", 9, 5, 2.7),
]


def _build_catalog() -> list[dict]:
    out = []
    for title, url, summary, category, recommended, resolved, total_hours in _RAW:
        workflow = find_workflow(category)
        out.append({
            "title": title, "url": url, "summary": summary, "category": category,
            "success_rate": round(resolved / recommended, 4) if recommended else 0.0,
            "avg_resolution_hours": round(total_hours / resolved, 4) if resolved else None,
            "workflow_available": workflow is not None,
            "workflow_title": (workflow or {}).get("title"),
            "workflow_steps": (workflow or {}).get("steps", []),
        })
    return out


KB_CATALOG = _build_catalog()


def _category_keywords(category: str) -> list[str]:
    return [w.strip().lower() for part in category.split("/") for w in part.split() if len(w.strip()) > 2]


def match_kb_docs(team: str, title: str, description: str, top_k: int = 3) -> tuple[list[dict], bool]:
    """Rank the static catalog by keyword overlap against the routed team +
    ticket text, tie-broken by success rate (the best-proven doc first).
    Falls back to the catalog's best-proven docs if nothing matched.

    Returns (ranked_docs, gap_detected). gap_detected=True means no catalog doc
    matched by keyword — the returned docs are the best-proven fallbacks, not
    genuine matches, signalling that no KB article exists for this issue type yet."""
    haystack = f"{team} {title} {description}".lower()
    scored = []
    for doc in KB_CATALOG:
        score = sum(1 for k in _category_keywords(doc["category"]) if k in haystack)
        if doc["category"].lower() in haystack:
            score += 2
        scored.append((score, doc))
    scored.sort(key=lambda t: (-t[0], -t[1]["success_rate"]))
    ranked = [d for s, d in scored if s > 0][:top_k]
    gap_detected = not ranked
    if gap_detected:
        ranked = sorted(KB_CATALOG, key=lambda d: -d["success_rate"])[:top_k]
    return ranked, gap_detected
