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
    # ── D365 Finance workflows (checked first — Finance keywords are specific
    #    enough not to collide with Kubernetes; Kubernetes keywords like "pending"
    #    can appear in Finance ticket text so Finance must win the ordering) ────
    (("vendor invoice", "accounts payable", "ap invoice", "invoice posting", "fiscal period",
      "invoice pending", "invoice stuck", "posting profile", "voucher", "three-way match",
      "accounts payable", "payment journal"), {
        "title": "Resolve vendor invoice posting failure (D365 Finance AP)",
        "steps": [
            "Check the fiscal period status: General Ledger → Ledger calendars → confirm period is Open for AP module.",
            "Verify the vendor posting profile has the correct summary account configured.",
            "Confirm three-way matching is complete (PO → receipt → invoice quantities match).",
            "Check vendor account for any payment holds or blocked status.",
            "If a currency mismatch, verify the exchange rate type on the invoice matches the posting configuration.",
            "Post the invoice and confirm the voucher is created in the GL sub-ledger.",
        ],
    }),
    (("general ledger", "journal", "unbalanced", "voucher", "ledger journal",
      "trial balance", "period close", "gl journal", "debit credit", "journal posting"), {
        "title": "Fix unbalanced GL journal and complete period close (D365 Finance)",
        "steps": [
            "Open the journal and verify total debits equal total credits across all voucher lines.",
            "Check for any lines with a missing or invalid main account.",
            "Verify all financial dimensions on each line are valid combinations per the account structure.",
            "If a rounding difference, enable 'Penny difference tolerance' in GL Parameters.",
            "Post the corrected journal and run the trial balance report to confirm zero difference.",
            "Complete the period-close checklist and change the period status to Closed.",
        ],
    }),
    (("accounts receivable", "customer invoice", "ar invoice", "customer payment",
      "settlement", "aging", "overdue invoice", "collection letter", "dunning"), {
        "title": "Settle customer payment against open invoice (D365 Finance AR)",
        "steps": [
            "Navigate to Accounts Receivable → Transactions → Settle open transactions.",
            "Select the customer account and identify the open invoice and the matching payment.",
            "Verify the payment currency matches the invoice currency (or apply exchange rate difference).",
            "Apply any eligible cash discount if the payment is within the discount period.",
            "Mark both transactions and click Settle — confirm the invoice status changes to Closed.",
            "Run the AR aging report to verify the balance is cleared.",
        ],
    }),
    (("fixed asset", "depreciation", "asset book", "asset register",
      "acquisition", "net book value", "fa module", "asset depreciation"), {
        "title": "Re-run fixed asset depreciation proposal (D365 Finance)",
        "steps": [
            "Navigate to Fixed Assets → Journals → Depreciation journal.",
            "Verify the depreciation start date on the asset book is in the past (not future-dated).",
            "Confirm the depreciation profile is assigned: method, service life, and period frequency.",
            "Run the depreciation proposal for the affected asset group and period.",
            "Review the generated lines and confirm amounts match the expected calculation.",
            "Post the journal and verify the net book value updates correctly on the asset record.",
        ],
    }),
    (("inventory", "on-hand", "on hand", "negative inventory", "inventory adjustment",
      "cycle count", "inventory closing", "item quantity", "warehouse"), {
        "title": "Correct negative inventory and post adjustment (D365 Finance / SCM)",
        "steps": [
            "Navigate to Inventory Management → Journals → Inventory adjustment.",
            "Create a new journal line for the affected item and site/warehouse.",
            "Enter a positive quantity to offset the negative on-hand balance.",
            "Verify the cost price is set correctly (use item's current moving average or standard cost).",
            "Post the adjustment journal and confirm on-hand is now positive.",
            "Review inventory transactions to identify the root cause (over-pick, missing receipt, etc.).",
        ],
    }),
    (("batch job", "batch error", "batch failed", "batch stuck", "recurring job",
      "dmf import", "data entity", "staging table", "data management", "integration error"), {
        "title": "Clear DMF staging error and reimport data (D365 Finance)",
        "steps": [
            "Navigate to Data Management → Job history → locate the failed import job.",
            "Review the error log to identify the failing record and field.",
            "Click 'Clean up staging' to clear the stale staging records.",
            "Correct the source file based on the error (missing field, wrong format, invalid value).",
            "Re-run the import job and monitor the execution log for completion.",
            "Validate the imported records in the target entity (e.g., vendor accounts, GL journals).",
        ],
    }),
    # ── Kubernetes / Karpenter workflows ──────────────────────────────────────
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
