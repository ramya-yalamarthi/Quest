"""
Finance AI — answers natural language questions grounded in real D365 Finance data.

Flow:
  1. Classify the question to know which Finance entity to fetch
  2. Fetch that data from FinanceODataClient
  3. Pass the data + question to the LLM
  4. Return a structured answer with supporting data rows

If the Finance OData client is not configured (no FINANCE_URL), the module
falls back to telling the caller Finance data is not connected.
"""

from __future__ import annotations

import json
from typing import Optional

from app.orchestrator.finance_odata import FinanceODataClient, available
from app.orchestrator.llm import chat_json, llm_available

# ── entity routing ────────────────────────────────────────────────────────────
# Maps question keywords → which Finance entity to fetch

_ENTITY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("vendor_invoices",    ["vendor invoice", "vendor payment", "accounts payable",
                             "ap invoice", "invoice pending", "invoice stuck",
                             "vendor", "payable", "purchase invoice", "po invoice"]),
    ("gl_journals",        ["journal", "general ledger", "gl journal", "ledger journal",
                             "unbalanced", "voucher", "posting", "debit", "credit",
                             "trial balance", "period close", "journal posting"]),
    ("fiscal_periods",     ["fiscal period", "period open", "period closed", "period status",
                             "ledger calendar", "accounting period", "fiscal calendar"]),
    ("fixed_assets",       ["fixed asset", "asset depreciation", "depreciation", "asset book",
                             "acquisition", "net book value", "asset register", "fa module"]),
    ("inventory",          ["inventory", "on-hand", "on hand", "stock", "warehouse",
                             "item quantity", "negative inventory", "inventory level"]),
    ("batch_jobs",         ["batch job", "batch error", "batch failed", "batch stuck",
                             "recurring job", "scheduled job", "batch status"]),
    ("customer_invoices",  ["customer invoice", "accounts receivable", "ar invoice",
                             "customer payment", "overdue invoice", "aged receivables"]),
]


def _classify_question(question: str) -> str:
    """Return the entity name that best matches the question."""
    q = question.lower()
    best_entity = "vendor_invoices"
    best_score = 0
    for entity, keywords in _ENTITY_KEYWORDS:
        score = sum(1 for k in keywords if k in q)
        if score > best_score:
            best_score = score
            best_entity = entity
    return best_entity


def _fetch_data(client: FinanceODataClient, entity: str) -> tuple[list[dict], str]:
    """Fetch the relevant Finance records and return (rows, entity_label)."""
    if entity == "vendor_invoices":
        return client.get_vendor_invoices(top=15), "Vendor Invoices"
    if entity == "gl_journals":
        return client.get_gl_journals(top=15), "GL Journals"
    if entity == "fiscal_periods":
        return client.get_fiscal_periods(), "Fiscal Periods"
    if entity == "fixed_assets":
        return client.get_fixed_assets(top=15), "Fixed Assets"
    if entity == "inventory":
        return client.get_inventory_onhand(top=15), "Inventory On-Hand"
    if entity == "batch_jobs":
        return client.get_batch_jobs(top=15), "Batch Jobs"
    if entity == "customer_invoices":
        return client.get_customer_invoices(top=15), "Customer Invoices"
    return [], "Unknown"


def _build_system_prompt() -> str:
    return (
        "You are a Dynamics 365 Finance expert AI assistant. "
        "You are given real Finance data fetched live from the D365 Finance OData API. "
        "Answer the user's question accurately and concisely, grounded only in the data provided. "
        "If the data does not contain enough information to answer fully, say so clearly. "
        "Always:\n"
        "- Identify specific records by their number/ID\n"
        "- Highlight anomalies (unbalanced journals, negative inventory, failed batch jobs, "
        "  overdue invoices, closed fiscal periods)\n"
        "- Give a clear direct answer first, then supporting detail\n"
        "- Keep the answer under 300 words\n"
        "Respond as JSON: {\"answer\": \"...\", \"anomalies\": [...], \"records_referenced\": [...], \"confidence\": \"high|medium|low\"}"
    )


def answer_finance_question(question: str) -> dict:
    """
    Main entry point. Given a natural language question about Finance data,
    fetch the relevant D365 Finance records and return an AI-generated answer.

    Returns:
        {
          "answer":             str,
          "entity_fetched":     str,
          "records":            list[dict],   # raw data shown to the AI
          "anomalies":          list[str],
          "records_referenced": list[str],
          "confidence":         str,
          "finance_connected":  bool,
          "llm_available":      bool,
          "error":              str | None,
        }
    """
    if not available():
        return {
            "answer": (
                "D365 Finance is not connected. Add the FINANCE_URL environment variable "
                "(e.g. https://your-env.operations.dynamics.com) to enable live Finance data."
            ),
            "entity_fetched": None,
            "records": [],
            "anomalies": [],
            "records_referenced": [],
            "confidence": "low",
            "finance_connected": False,
            "llm_available": llm_available(),
            "error": "FINANCE_URL not configured",
        }

    entity = _classify_question(question)

    try:
        client = FinanceODataClient()
        records, entity_label = _fetch_data(client, entity)
    except Exception as exc:
        return {
            "answer": f"Could not fetch Finance data: {exc}",
            "entity_fetched": entity,
            "records": [],
            "anomalies": [],
            "records_referenced": [],
            "confidence": "low",
            "finance_connected": True,
            "llm_available": llm_available(),
            "error": str(exc),
        }

    if not records:
        return {
            "answer": f"No {entity_label} records found in D365 Finance for the current query.",
            "entity_fetched": entity_label,
            "records": [],
            "anomalies": [],
            "records_referenced": [],
            "confidence": "low",
            "finance_connected": True,
            "llm_available": llm_available(),
            "error": None,
        }

    # Limit data sent to LLM to avoid token overload
    data_snippet = json.dumps(records[:10], indent=2, default=str)
    user_prompt = (
        f"Finance entity: {entity_label}\n"
        f"Total records fetched: {len(records)}\n\n"
        f"Data:\n{data_snippet}\n\n"
        f"Question: {question}"
    )

    llm_result = chat_json(_build_system_prompt(), user_prompt, max_tokens=600)

    if llm_result:
        return {
            "answer":             llm_result.get("answer", ""),
            "entity_fetched":     entity_label,
            "records":            records,
            "anomalies":          llm_result.get("anomalies", []),
            "records_referenced": llm_result.get("records_referenced", []),
            "confidence":         llm_result.get("confidence", "medium"),
            "finance_connected":  True,
            "llm_available":      True,
            "error":              None,
        }

    # LLM not available — do a simple rule-based answer
    anomalies = _rule_based_anomalies(entity, records)
    return {
        "answer": _rule_based_answer(entity, records, anomalies, question),
        "entity_fetched":     entity_label,
        "records":            records,
        "anomalies":          anomalies,
        "records_referenced": [],
        "confidence":         "medium",
        "finance_connected":  True,
        "llm_available":      False,
        "error":              None,
    }


def _rule_based_anomalies(entity: str, records: list[dict]) -> list[str]:
    """Surface obvious problems from the data without using the LLM."""
    issues = []
    if entity == "vendor_invoices":
        stuck = [r["invoice_number"] for r in records if r.get("posting_status") == "Pending"]
        if stuck:
            issues.append(f"{len(stuck)} vendor invoice(s) stuck in Pending: {', '.join(stuck[:5])}")
    if entity == "gl_journals":
        unbal = [r["journal_number"] for r in records if not r.get("balanced")]
        if unbal:
            issues.append(f"{len(unbal)} unbalanced journal(s): {', '.join(str(j) for j in unbal[:5])}")
        unposted = [r["journal_number"] for r in records if not r.get("posted")]
        if unposted:
            issues.append(f"{len(unposted)} unposted journal(s) found")
    if entity == "fiscal_periods":
        on_hold = [r["period"] for r in records if r.get("on_hold")]
        if on_hold:
            issues.append(f"Periods on hold: {', '.join(on_hold[:5])}")
    if entity == "inventory":
        neg = [r["item_number"] for r in records if r.get("negative")]
        if neg:
            issues.append(f"Negative on-hand inventory: {', '.join(neg[:5])}")
    if entity == "batch_jobs":
        failed = [r["description"] for r in records if r.get("status") == "Error"]
        if failed:
            issues.append(f"{len(failed)} failed batch job(s): {', '.join(failed[:3])}")
    return issues


def _rule_based_answer(entity: str, records: list[dict], anomalies: list[str],
                        question: str) -> str:
    count = len(records)
    base = f"Fetched {count} {entity.replace('_', ' ')} record(s) from D365 Finance. "
    if anomalies:
        base += "Issues found: " + "; ".join(anomalies) + "."
    else:
        base += "No obvious anomalies detected in the fetched records."
    return base
