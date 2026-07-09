"""
Dynamics 365 Finance OData client.

Reads real Finance data — vendor invoices, GL journals, fiscal periods,
fixed assets, inventory, and batch jobs — directly from the D365 Finance
OData API so the AI can answer questions grounded in actual transaction data.

Required env vars (add to Render + .env):
    FINANCE_URL          e.g. https://your-env.operations.dynamics.com
    AZURE_TENANT_ID      (same as Dataverse)
    AZURE_CLIENT_ID      (same as Dataverse)
    AZURE_CLIENT_SECRET  (same as Dataverse)

If FINANCE_URL is not set, available() returns False and callers fall back
gracefully — same pattern as the Dataverse client.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

_ODATA_VERSION = "v9.1"


def _env() -> Optional[dict]:
    base = os.getenv("FINANCE_URL")
    tenant = os.getenv("AZURE_TENANT_ID")
    cid = os.getenv("AZURE_CLIENT_ID")
    secret = os.getenv("AZURE_CLIENT_SECRET")
    if not all([base, tenant, cid, secret]):
        return None
    return {"base": base.rstrip("/"), "tenant": tenant, "cid": cid, "secret": secret}


def available() -> bool:
    return _env() is not None


class FinanceODataClient:
    """
    Reads D365 Finance entities via OData.
    Same auth pattern as DataverseClient — client_credentials, token cached.
    """

    def __init__(self, cfg: Optional[dict] = None, timeout: int = 30) -> None:
        self.cfg = cfg or _env()
        if self.cfg is None:
            raise RuntimeError("FINANCE_URL env var not set.")
        self.timeout = timeout
        self._token: Optional[str] = None
        self._token_exp: float = 0.0

    # ── auth ──────────────────────────────────────────────────────────────
    def _get_token(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        url = (f"https://login.microsoftonline.com/{self.cfg['tenant']}"
               f"/oauth2/v2.0/token")
        body = urllib.parse.urlencode({
            "grant_type":    "client_credentials",
            "client_id":     self.cfg["cid"],
            "client_secret": self.cfg["secret"],
            "scope":         f"{self.cfg['base']}/.default",
        }).encode()
        req = urllib.request.Request(url, data=body, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = json.loads(r.read())
        self._token    = data["access_token"]
        self._token_exp = time.time() + int(data.get("expires_in", 3600))
        return self._token

    # ── low-level ─────────────────────────────────────────────────────────
    def _get(self, entity: str, params: dict | None = None) -> list[dict]:
        """GET /data/<entity>?<params> — returns the value list."""
        qs = urllib.parse.urlencode(params or {})
        url = f"{self.cfg['base']}/data/{entity}?{qs}" if qs else f"{self.cfg['base']}/data/{entity}"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {self._get_token()}",
            "Accept":        "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version":    "4.0",
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read()).get("value", [])
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Finance OData {entity} → HTTP {e.code}: {e.read()[:200]}")

    # ── Finance entities ──────────────────────────────────────────────────

    def get_vendor_invoices(self, top: int = 20, status: str | None = None) -> list[dict]:
        """
        Fetch pending/recent vendor invoices from VendorInvoiceHeaderV2Entity.
        status: 'Pending' | 'Approved' | 'Posted' | None (all)
        """
        params = {
            "$top": top,
            "$orderby": "InvoiceDate desc",
            "$select": ("InvoiceNumber,VendorAccountNumber,InvoiceDate,"
                        "TotalInvoiceAmount,CurrencyCode,ApprovalStatus,"
                        "PostingStatus,LegalEntityId,PaymentDueDate,Description"),
        }
        if status:
            params["$filter"] = f"ApprovalStatus eq '{status}'"
        rows = self._get("VendorInvoiceHeadersV2", params)
        return [{
            "invoice_number":   r.get("InvoiceNumber"),
            "vendor":           r.get("VendorAccountNumber"),
            "date":             (r.get("InvoiceDate") or "")[:10],
            "amount":           r.get("TotalInvoiceAmount"),
            "currency":         r.get("CurrencyCode"),
            "approval_status":  r.get("ApprovalStatus"),
            "posting_status":   r.get("PostingStatus"),
            "legal_entity":     r.get("LegalEntityId"),
            "due_date":         (r.get("PaymentDueDate") or "")[:10],
            "description":      r.get("Description"),
        } for r in rows]

    def get_gl_journals(self, top: int = 20, posted: bool | None = None) -> list[dict]:
        """
        Fetch General Ledger journals from LedgerJournalHeaderEntity.
        posted: True = only posted, False = only unposted, None = all
        """
        params = {
            "$top": top,
            "$orderby": "TransDate desc",
            "$select": ("JournalBatchNumber,JournalName,Description,"
                        "Posted,TransDate,LegalEntity,TotalDebit,TotalCredit"),
        }
        if posted is True:
            params["$filter"] = "Posted eq true"
        elif posted is False:
            params["$filter"] = "Posted eq false"
        rows = self._get("LedgerJournalHeaders", params)
        return [{
            "journal_number": r.get("JournalBatchNumber"),
            "journal_name":   r.get("JournalName"),
            "description":    r.get("Description"),
            "posted":         r.get("Posted"),
            "date":           (r.get("TransDate") or "")[:10],
            "legal_entity":   r.get("LegalEntity"),
            "total_debit":    r.get("TotalDebit"),
            "total_credit":   r.get("TotalCredit"),
            "balanced":       abs((r.get("TotalDebit") or 0) - (r.get("TotalCredit") or 0)) < 0.01,
        } for r in rows]

    def get_fiscal_periods(self, legal_entity: str | None = None) -> list[dict]:
        """
        Fetch fiscal period open/closed status from FiscalCalendarPeriodEntity.
        """
        params = {
            "$top": 50,
            "$select": ("FiscalCalendarName,PeriodName,StartDate,EndDate,"
                        "LedgerFiscalPeriodType,IsOnHold,LegalEntityId"),
            "$orderby": "StartDate desc",
        }
        if legal_entity:
            params["$filter"] = f"LegalEntityId eq '{legal_entity}'"
        rows = self._get("FiscalCalendarPeriods", params)
        return [{
            "calendar":      r.get("FiscalCalendarName"),
            "period":        r.get("PeriodName"),
            "start":         (r.get("StartDate") or "")[:10],
            "end":           (r.get("EndDate") or "")[:10],
            "type":          r.get("LedgerFiscalPeriodType"),
            "on_hold":       r.get("IsOnHold"),
            "legal_entity":  r.get("LegalEntityId"),
            "status":        "On hold" if r.get("IsOnHold") else "Open",
        } for r in rows]

    def get_fixed_assets(self, top: int = 20, status: str | None = None) -> list[dict]:
        """
        Fetch fixed assets from AssetAssetEntity.
        status: 'Open' | 'Closed' | 'WriteOff' | None
        """
        params = {
            "$top": top,
            "$select": ("AssetNumber,AssetName,AssetGroupId,AcquisitionDate,"
                        "AcquisitionCost,AssetStatus,BookId,DepreciationMethod,"
                        "LegalEntityId,NetBookValue"),
            "$orderby": "AcquisitionDate desc",
        }
        if status:
            params["$filter"] = f"AssetStatus eq '{status}'"
        rows = self._get("AssetAssets", params)
        return [{
            "asset_number":      r.get("AssetNumber"),
            "name":              r.get("AssetName"),
            "group":             r.get("AssetGroupId"),
            "acquisition_date":  (r.get("AcquisitionDate") or "")[:10],
            "acquisition_cost":  r.get("AcquisitionCost"),
            "net_book_value":    r.get("NetBookValue"),
            "status":            r.get("AssetStatus"),
            "book":              r.get("BookId"),
            "depreciation":      r.get("DepreciationMethod"),
            "legal_entity":      r.get("LegalEntityId"),
        } for r in rows]

    def get_inventory_onhand(self, item_id: str | None = None, top: int = 20) -> list[dict]:
        """
        Fetch on-hand inventory from InventoryOnhandMobileEntity.
        """
        params = {
            "$top": top,
            "$select": ("ItemNumber,ProductName,WarehouseId,InventoryQuantity,"
                        "PhysicalInvent,ReservedPhysical,OrderedInTotal,InventoryUnitSymbol"),
        }
        if item_id:
            params["$filter"] = f"ItemNumber eq '{item_id}'"
        rows = self._get("InventoryOnhand", params)
        return [{
            "item_number":   r.get("ItemNumber"),
            "product_name":  r.get("ProductName"),
            "warehouse":     r.get("WarehouseId"),
            "on_hand":       r.get("InventoryQuantity"),
            "physical":      r.get("PhysicalInvent"),
            "reserved":      r.get("ReservedPhysical"),
            "ordered":       r.get("OrderedInTotal"),
            "unit":          r.get("InventoryUnitSymbol"),
            "negative":      (r.get("InventoryQuantity") or 0) < 0,
        } for r in rows]

    def get_batch_jobs(self, top: int = 20, status: str | None = None) -> list[dict]:
        """
        Fetch batch job history from BatchJobEntity.
        status: 'Executing' | 'Error' | 'Ended' | 'Waiting' | None
        """
        params = {
            "$top": top,
            "$orderby": "StartDateTime desc",
            "$select": ("BatchJobId,Description,Status,StartDateTime,"
                        "EndDateTime,CompanyId,CreatedBy,AlertOnError"),
        }
        if status:
            params["$filter"] = f"Status eq '{status}'"
        rows = self._get("BatchJobs", params)
        return [{
            "job_id":       r.get("BatchJobId"),
            "description":  r.get("Description"),
            "status":       r.get("Status"),
            "started":      (r.get("StartDateTime") or "")[:19].replace("T", " "),
            "ended":        (r.get("EndDateTime") or "")[:19].replace("T", " "),
            "company":      r.get("CompanyId"),
            "created_by":   r.get("CreatedBy"),
            "alert_on_err": r.get("AlertOnError"),
        } for r in rows]

    def get_customer_invoices(self, top: int = 20, status: str | None = None) -> list[dict]:
        """
        Fetch customer invoices from CustInvoiceJournalHeaderEntity.
        """
        params = {
            "$top": top,
            "$orderby": "InvoiceDate desc",
            "$select": ("InvoiceNumber,OrderAccount,InvoiceDate,DueDate,"
                        "InvoiceAmountMST,CurrencyCode,InvoiceStatus,"
                        "CustomerRef,DataAreaId"),
        }
        if status:
            params["$filter"] = f"InvoiceStatus eq '{status}'"
        rows = self._get("CustInvoiceJournalHeaders", params)
        return [{
            "invoice_number": r.get("InvoiceNumber"),
            "customer":       r.get("OrderAccount"),
            "date":           (r.get("InvoiceDate") or "")[:10],
            "due_date":       (r.get("DueDate") or "")[:10],
            "amount":         r.get("InvoiceAmountMST"),
            "currency":       r.get("CurrencyCode"),
            "status":         r.get("InvoiceStatus"),
            "reference":      r.get("CustomerRef"),
            "legal_entity":   r.get("DataAreaId"),
        } for r in rows]
