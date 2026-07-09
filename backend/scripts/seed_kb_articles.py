"""Seed the kb_articles catalog with real Kubernetes/Karpenter troubleshooting
guides, so the popup's Knowledge Base Recommendations section isn't empty.

Run ONCE against the live DB, after scripts/kb_tables.sql:
    cd backend && python -m scripts.seed_kb_articles

Requires the same env as the backend app (DATABASE_URL + an embedding
provider -- EMBEDDING_PROVIDER=local|cloud). Safe to re-run: skips any
article whose title already exists.

NOTE on the usage-stat columns (times_recommended/times_resolved/
total_resolution_hours): these are SEED/DEMO placeholders, not derived from
real resolved tickets -- same caveat as the engineer roster's track-record
columns. They exist so the popup's "% resolved" / "avg time" aren't all
blank on day one; real engineer thumbs-up feedback (kb_feedback ->
record_kb_outcome) is what should grow these numbers from here.
"""
from __future__ import annotations

from app.db.session import SessionLocal
from app.db.models.kb_article import KBArticle
from app.utils.embeddings import get_embedding

# (title, url, summary, category, times_recommended, times_resolved, total_resolution_hours)
ARTICLES = [
    (
        "NodePool quota exhausted — capacity grace period and manual drain procedure",
        "https://karpenter.sh/docs/concepts/nodepools/",
        "When a NodePool's instance-type/capacity quota is exhausted, Karpenter can't "
        "provision new nodes and pods stay Pending. Raise the NodePool's limits, then "
        "cordon and manually drain any nodes stuck mid-termination before retrying.",
        "Instance types / pricing",
        46, 39, 14.3,
    ),
    (
        "Pods stuck Pending — NodePool provisioning health-check",
        "https://karpenter.sh/docs/troubleshooting/",
        "Pods stuck in Pending usually trace back to the Karpenter controller, NodePool, "
        "or EC2NodeClass not provisioning. Checklist: controller health, NodePool/"
        "EC2NodeClass status, and cloud-provider quota limits blocking new nodes.",
        "Provisioning / scheduling",
        58, 49, 12.1,
    ),
    (
        "Cluster autoscaler not scaling up under load — policy tuning guide",
        "https://kubernetes.io/docs/concepts/cluster-administration/cluster-autoscaling/",
        "If CPU/memory pressure is high but the autoscaler isn't adding nodes, check the "
        "scale-up policy thresholds and recent scale-up/scale-down decision logs before "
        "assuming a hard capacity limit.",
        "Autoscaling / scaling",
        34, 27, 9.5,
    ),
    (
        "Node drain hangs and pods get force-deleted before EC2 terminates",
        "https://karpenter.sh/docs/concepts/disruption/",
        "NodeRepair / termination can set a grace period that ends up negative, bypassing "
        "normal pod shutdown sequencing and force-deleting pods before the underlying "
        "instance actually terminates -- causing overlapping old/new container lifecycles.",
        "Termination / eviction",
        21, 12, 5.8,
    ),
    (
        "Karpenter consolidation/disruption budget not triggering scale-down",
        "https://karpenter.sh/docs/concepts/disruption/#disruption-budgets",
        "Idle nodes not consolidating despite disruption budgets allowing it is usually a "
        "drift/consolidation eligibility issue -- check do-not-disrupt annotations and "
        "consolidateAfter timing on the NodePool.",
        "Consolidation / disruption",
        19, 11, 6.4,
    ),
    (
        "EC2NodeClass misconfiguration — subnet, AMI, and security group errors",
        "https://karpenter.sh/docs/concepts/nodeclasses/",
        "EC2NodeClass stuck unreconciled most often traces to a missing subnet, an AMI "
        "selector matching nothing, or a security group reference that no longer exists.",
        "Config / API (EC2NodeClass)",
        15, 9, 4.2,
    ),
    (
        "Karpenter controller metrics and observability gaps",
        "https://karpenter.sh/docs/reference/metrics/",
        "When cost/utilization metrics look wrong (negative values, missing series), check "
        "the controller logs first -- most reporting bugs trace to a reconciler error, not "
        "an actual infrastructure problem.",
        "Metrics / observability",
        12, 7, 3.9,
    ),
    (
        "Pod networking / DNS connectivity issues on newly provisioned nodes",
        "https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/",
        "New nodes failing DNS resolution or VPC connectivity is usually a security-group "
        "or subnet route table gap introduced by a NodePool/EC2NodeClass change, not a "
        "cluster DNS service issue.",
        "Networking",
        9, 5, 2.7,
    ),

    # ── Dynamics 365 Finance ────────────────────────────────────────────────────
    (
        "Vendor invoice posting fails — fiscal period not open",
        "https://learn.microsoft.com/en-us/dynamics365/finance/accounts-payable/vendor-invoices-overview",
        "When a vendor invoice cannot be posted and the infolog shows 'Period is not open', "
        "the target fiscal period in the General Ledger calendar is either closed or does not exist. "
        "Open the period in General Ledger > Calendars > Ledger calendars, or post to a different date.",
        "Accounts Payable",
        42, 38, 0.5,
    ),
    (
        "General ledger journal cannot be posted — unbalanced voucher",
        "https://learn.microsoft.com/en-us/dynamics365/finance/general-ledger/general-journal-processing",
        "An unbalanced voucher error means debits do not equal credits on one or more voucher lines. "
        "Check the offset account configuration on the journal name, verify currency rounding settings, "
        "and confirm that no lines have been accidentally deleted.",
        "General Ledger / Accounting",
        55, 51, 0.4,
    ),
    (
        "Fixed asset depreciation not running in batch",
        "https://learn.microsoft.com/en-us/dynamics365/finance/fixed-assets/depreciation-methods-conventions",
        "If the depreciation proposal batch job completes without creating transactions, check that the "
        "asset value model has a depreciation profile assigned, the acquisition date falls within the "
        "selected period, and the batch job user has the correct security role.",
        "Fixed Assets",
        28, 24, 0.8,
    ),
    (
        "Customer payment not settling against invoice — marking mismatch",
        "https://learn.microsoft.com/en-us/dynamics365/finance/accounts-receivable/settle-transactions-overview",
        "When a customer payment exists but does not settle against an open invoice, the most common "
        "causes are: currency mismatch, settlement tolerance exceeded, or the payment and invoice are "
        "in different legal entities. Use Accounts Receivable > Transactions > Settle open transactions.",
        "Accounts Receivable",
        33, 29, 0.6,
    ),
    (
        "Data entity import fails with staging table error",
        "https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/data-entities/data-import-export-job",
        "A staging table error during DMF import usually means the staging table has stale records from "
        "a previous failed run, or the field mapping is missing a required column. Clear the staging data "
        "from the job history, re-map fields, and re-run the import in validate-only mode first.",
        "Batch Jobs / Integration",
        37, 31, 1.1,
    ),
    (
        "Inventory on-hand shows negative quantity — adjustment procedure",
        "https://learn.microsoft.com/en-us/dynamics365/supply-chain/inventory/inventory-adjustment-journal",
        "Negative on-hand inventory occurs when sales or production transactions consume stock before "
        "the corresponding receipt is posted. Run the Inventory closing procedure, then post an "
        "inventory adjustment journal to correct the physical quantity to the correct value.",
        "Inventory / Warehouse",
        21, 17, 1.4,
    ),
]


def main():
    db = SessionLocal()
    try:
        added = 0
        for title, url, summary, category, times_rec, times_res, total_hours in ARTICLES:
            if db.query(KBArticle).filter(KBArticle.title == title).first():
                continue
            embedding = get_embedding(f"{title}\n{summary}")
            db.add(KBArticle(
                title=title, url=url, summary=summary, category=category,
                embedding=embedding, times_recommended=times_rec,
                times_resolved=times_res, total_resolution_hours=total_hours,
            ))
            added += 1
        db.commit()
        print(f"Seeded {added} new KB article(s); {len(ARTICLES) - added} already existed.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
