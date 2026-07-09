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
    # ── D365 Finance KB articles ──────────────────────────────────────────────
    ("Vendor invoice stuck in Pending — fiscal period and posting profile fix",
     "https://learn.microsoft.com/en-us/dynamics365/finance/accounts-payable/vendor-invoices-overview",
     "Vendor invoices fail to post when the fiscal period is closed for the AP module or the vendor "
     "posting profile is missing a summary account. Open the period in Ledger calendars for the AP "
     "module, verify the posting profile, and confirm three-way match is complete before reposting.",
     "Accounts Payable / vendor invoices", 52, 46, 18.5),
    ("Unbalanced GL journal — voucher and penny difference troubleshooting",
     "https://learn.microsoft.com/en-us/dynamics365/finance/general-ledger/general-journal-processing",
     "GL journals fail to post when total debits do not equal total credits on a voucher, or when "
     "a rounding penny difference exceeds the configured tolerance. Enable 'Penny difference tolerance' "
     "in GL Parameters and verify all lines have valid main accounts and dimension combinations.",
     "General Ledger / journal posting", 44, 38, 14.2),
    ("Fixed asset depreciation proposal not generating transactions",
     "https://learn.microsoft.com/en-us/dynamics365/finance/fixed-assets/depreciation-methods-conventions",
     "The depreciation proposal generates zero entries when the asset's depreciation start date is "
     "set in the future, the depreciation profile is missing, or the asset book period is closed. "
     "Verify the start date, profile assignment, and that the book calendar period is open.",
     "Fixed Assets / depreciation", 38, 33, 11.8),
    ("Customer payment not settling against open invoice — AR settlement fix",
     "https://learn.microsoft.com/en-us/dynamics365/finance/accounts-receivable/settle-partial-customer-payment",
     "Customer payments fail to settle when posted to a different account than the invoice, when "
     "a currency mismatch exists, or when the settlement date falls outside the cash discount period. "
     "Use Settle open transactions to manually match the payment to the correct invoice.",
     "Accounts Receivable / customer payment", 41, 35, 13.1),
    ("DMF import staging table error — cleanup and reimport procedure",
     "https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/data-import-export-job",
     "Data Management Framework imports fail when the staging table contains stale records from a "
     "previous failed run. Clean up staging via Data Management → Job history → Clean up staging, "
     "correct the source file based on the error log, and re-run the import.",
     "Batch Jobs / integration", 35, 29, 9.7),
    ("Negative inventory adjustment after sales order over-pick",
     "https://learn.microsoft.com/en-us/dynamics365/supply-chain/inventory/inventory-journals",
     "Negative on-hand inventory results from over-picking, missing product receipts, or incorrect "
     "inventory transactions. Post an inventory adjustment journal with a positive quantity to correct "
     "the balance, then investigate the root cause transaction using inventory transaction history.",
     "Inventory / on-hand", 29, 24, 8.4),
]
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


_FINANCE_KEYWORDS = [
    "vendor invoice", "accounts payable", "accounts receivable", "general ledger",
    "fixed asset", "depreciation", "fiscal period", "voucher", "ledger journal",
    "ap invoice", "ar invoice", "customer invoice", "inventory adjustment",
    "batch job", "dmf", "data entity", "d365 finance", "dynamics finance",
    "posting profile", "tax", "vat", "gst", " gl ", " ap ", " ar ", " fa ",
]

_FINANCE_CATEGORIES = {
    "accounts payable", "vendor invoices", "general ledger", "journal posting",
    "fixed assets", "depreciation", "accounts receivable", "customer payment",
    "batch jobs", "integration", "inventory", "on-hand",
}


def _is_finance_ticket(haystack: str) -> bool:
    return any(k in haystack for k in _FINANCE_KEYWORDS)


def match_kb_docs(team: str, title: str, description: str, top_k: int = 3) -> tuple[list[dict], bool]:
    """Rank the static catalog by keyword overlap against the routed team +
    ticket text, tie-broken by success rate (the best-proven doc first).

    Domain-aware: Finance tickets are matched only against Finance KB articles,
    and Kubernetes tickets against Kubernetes articles, so recommendations are
    never cross-domain.

    Returns (ranked_docs, gap_detected). gap_detected=True means no catalog doc
    matched by keyword — the returned docs are the best-proven fallbacks, not
    genuine matches, signalling that no KB article exists for this issue type yet."""
    haystack = f"{team} {title} {description}".lower()
    finance = _is_finance_ticket(haystack)

    # Filter catalog to domain-relevant articles only
    domain_catalog = [
        doc for doc in KB_CATALOG
        if finance == any(cat in doc["category"].lower() for cat in _FINANCE_CATEGORIES)
    ]
    if not domain_catalog:
        domain_catalog = KB_CATALOG  # safety fallback

    scored = []
    for doc in domain_catalog:
        score = sum(1 for k in _category_keywords(doc["category"]) if k in haystack)
        if doc["category"].lower() in haystack:
            score += 2
        # Also score on keyword overlap with title/summary
        summary_kws = [w.strip().lower() for w in doc["title"].split() if len(w) > 3]
        score += sum(1 for k in summary_kws if k in haystack)
        scored.append((score, doc))
    scored.sort(key=lambda t: (-t[0], -t[1]["success_rate"]))
    ranked = [d for s, d in scored if s > 0][:top_k]
    gap_detected = not ranked
    if gap_detected:
        ranked = sorted(domain_catalog, key=lambda d: -d["success_rate"])[:top_k]
    return ranked, gap_detected
