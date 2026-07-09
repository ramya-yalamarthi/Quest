"""
Dynamics 365 / Dataverse client for the orchestrator (Approach #2).

Reads Cases (the `incident` table) and writes the recommendation advisory back
as a Note (annotation) on the Case. Pure stdlib (urllib) -- no new pip deps.

Self-contained and OPTIONAL, mirroring llm.py: if the env vars aren't set,
``available()`` is False and callers fall back gracefully (the pipeline keeps
working on the 4 reference tickets, no D365 needed).

Required env vars (set on Render, never in code/git):
    DATAVERSE_URL        e.g. https://orgc409312b.crm.dynamics.com
    AZURE_TENANT_ID
    AZURE_CLIENT_ID
    AZURE_CLIENT_SECRET
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

API_VERSION = "v9.2"


def _env() -> Optional[dict]:
    base = os.getenv("DATAVERSE_URL")
    tenant = os.getenv("AZURE_TENANT_ID")
    cid = os.getenv("AZURE_CLIENT_ID")
    secret = os.getenv("AZURE_CLIENT_SECRET")
    if not all([base, tenant, cid, secret]):
        return None
    return {"base": base.rstrip("/"), "tenant": tenant, "cid": cid, "secret": secret}


def available() -> bool:
    return _env() is not None


class DataverseClient:
    """Minimal Dataverse Web API client. Construct once and reuse (token cached).

    All network methods raise on hard failure; callers in the orchestrator wrap
    calls and fall back, so a D365 outage never breaks the pipeline.
    """

    def __init__(self, cfg: Optional[dict] = None, timeout: int = 30) -> None:
        self.cfg = cfg or _env()
        if self.cfg is None:
            raise RuntimeError("Dataverse env vars not set (DATAVERSE_URL / AZURE_*).")
        self.timeout = timeout
        self._token: Optional[str] = None
        self._token_exp: float = 0.0

    # -- auth -------------------------------------------------------------
    def _get_token(self) -> str:
        # reuse the cached token until ~60s before expiry
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        url = f"https://login.microsoftonline.com/{self.cfg['tenant']}/oauth2/v2.0/token"
        body = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_id": self.cfg["cid"],
            "client_secret": self.cfg["secret"],
            "scope": f"{self.cfg['base']}/.default",
        }).encode()
        req = urllib.request.Request(url, data=body, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = json.loads(r.read())
        self._token = data["access_token"]
        self._token_exp = time.time() + int(data.get("expires_in", 3600))
        return self._token

    # -- low-level request ------------------------------------------------
    def _request(self, method: str, path: str, body: Optional[dict] = None,
                 extra_headers: Optional[dict] = None) -> Optional[dict]:
        url = f"{self.cfg['base']}/api/data/{API_VERSION}/{path.lstrip('/')}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self._get_token()}")
        req.add_header("Accept", "application/json")
        req.add_header("OData-MaxVersion", "4.0")
        req.add_header("OData-Version", "4.0")
        if body is not None:
            req.add_header("Content-Type", "application/json")
        for k, v in (extra_headers or {}).items():
            req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            raw = r.read()
            return json.loads(raw) if raw else None

    # -- create / customer (used by the GitHub-issue import script) -------
    def first_customer_bind(self) -> Optional[str]:
        """Return an @odata.bind to an existing account (or contact) to use as
        the required customer on imported cases. None if the org has neither."""
        acc = (self._request("GET", "accounts?$select=accountid&$top=1") or {}).get("value", [])
        if acc:
            return f"/accounts({acc[0]['accountid']})"
        con = (self._request("GET", "contacts?$select=contactid&$top=1") or {}).get("value", [])
        if con:
            return f"/contacts({con[0]['contactid']})"
        return None

    def create_incident(self, title: str, description: str, customer_bind: str) -> Optional[str]:
        """Create a Case (incident) and return its new id. `customer_bind` is the
        required customer, e.g. '/accounts(<guid>)'."""
        key = "customerid_account@odata.bind" if "/accounts(" in customer_bind \
            else "customerid_contact@odata.bind"
        body = {"title": (title or "Untitled")[:300], "description": description or "", key: customer_bind}
        resp = self._request("POST", "incidents", body,
                             extra_headers={"Prefer": "return=representation"})
        return (resp or {}).get("incidentid")

    # -- cases ------------------------------------------------------------
    def list_cases(self, top: int = 50, created_after: Optional[str] = None,
                   resolved_only: bool = False) -> list[dict]:
        """Return recent Cases as normalised dicts (newest first).

        created_after: ISO-8601 string; only cases created strictly after it.
        resolved_only: when True, return only resolved Cases (statecode 1) --
            used to build the similarity corpus, since only closed cases have a
            proven resolution worth learning from.
        """
        params = {
            "$select": "incidentid,ticketnumber,title,description,prioritycode,statecode,statuscode,createdon,overriddencreatedon",
            "$orderby": "createdon desc",
            "$top": str(top),
        }
        filters = []
        if created_after:
            filters.append(f"createdon gt {created_after}")
        if resolved_only:
            filters.append("statecode eq 1")
        if filters:
            params["$filter"] = " and ".join(filters)
        path = "incidents?" + urllib.parse.urlencode(params)
        data = self._request("GET", path) or {}
        return [self._normalise_case(c) for c in data.get("value", [])]

    @staticmethod
    def _normalise_case(c: dict) -> dict:
        return {
            "id": c.get("incidentid"),
            "ticket_number": c.get("ticketnumber"),
            "title": c.get("title") or "",
            "description": c.get("description") or "",
            "priority": c.get("prioritycode"),
            "status": c.get("statuscode"),
            "state": c.get("statecode"),       # 0 active/open, 1 resolved, 2 cancelled
            # Use overriddencreatedon if set (backdated demo/migration records); fall back to createdon
            "created_on": c.get("overriddencreatedon") or c.get("createdon"),
        }

    _CASE_SELECT = ("incidentid,ticketnumber,title,description,prioritycode,"
                    "statecode,statuscode,createdon,overriddencreatedon")

    def get_case(self, case_id: str) -> Optional[dict]:
        """Fetch one Case by its GUID (for the event-driven webhook). Returns
        None if the id doesn't resolve (404/400) rather than raising."""
        try:
            data = self._request("GET", f"incidents({case_id})?$select={self._CASE_SELECT}")
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return None
            raise
        return self._normalise_case(data) if data else None

    def get_case_by_number(self, ticket_number: str) -> Optional[dict]:
        """Fetch one Case by its ticket number (CAS-...)."""
        num = ticket_number.replace("'", "''")
        params = urllib.parse.urlencode({
            "$select": self._CASE_SELECT, "$top": "1",
            "$filter": f"ticketnumber eq '{num}'",
        })
        rows = (self._request("GET", "incidents?" + params) or {}).get("value", [])
        return self._normalise_case(rows[0]) if rows else None

    def case_has_note(self, case_id: str, subject: str) -> bool:
        """True if the Case already has an annotation with this subject (so the
        poller is idempotent and never double-posts).

        NOTE: the query params MUST be URL-encoded (the filter contains spaces);
        sending them raw makes Dataverse reject the request and this silently
        return False -- which previously broke the poller's seeding."""
        subj = subject.replace("'", "''")
        params = {
            "$select": "annotationid",
            "$top": "1",
            "$filter": f"_objectid_value eq {case_id} and subject eq '{subj}'",
        }
        path = "annotations?" + urllib.parse.urlencode(params)
        try:
            data = self._request("GET", path) or {}
            return bool(data.get("value"))
        except Exception:
            return False

    def list_case_notes(self, case_id: str, top: int = 50) -> list[dict]:
        """ALL notes on a Case (any subject), oldest first -- the basis for a
        handoff's conversation-history digest. Never raises; returns []."""
        params = urllib.parse.urlencode({
            "$select": "subject,notetext,createdon",
            "$filter": f"_objectid_value eq {case_id}",
            "$orderby": "createdon asc",
            "$top": str(top),
        })
        try:
            rows = (self._request("GET", "annotations?" + params) or {}).get("value", [])
        except Exception:
            return []
        return [{"subject": r.get("subject"), "notetext": r.get("notetext"),
                  "createdon": r.get("createdon")} for r in rows]

    # -- write-back -------------------------------------------------------
    def create_case_note(self, case_id: str, subject: str, text: str) -> Optional[str]:
        """Write a Note (annotation) onto a Case. Returns the new annotation id."""
        body = {
            "subject": subject,
            "notetext": text,
            "objectid_incident@odata.bind": f"/incidents({case_id})",
        }
        # ask Dataverse to return the created row so we get its id
        url = f"{self.cfg['base']}/api/data/{API_VERSION}/annotations"
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {self._get_token()}")
        req.add_header("Accept", "application/json")
        req.add_header("OData-MaxVersion", "4.0")
        req.add_header("OData-Version", "4.0")
        req.add_header("Content-Type", "application/json")
        req.add_header("Prefer", "return=representation")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            raw = r.read()
            out = json.loads(raw) if raw else {}
        return out.get("annotationid")

    def update_case_note(self, annotation_id: str, text: str) -> None:
        """Replace a Note's text -- used to fill in a placeholder note."""
        self._request("PATCH", f"annotations({annotation_id})", {"notetext": text})

    def delete_note(self, annotation_id: str) -> None:
        """Delete a Note (e.g. roll back a placeholder if processing failed)."""
        self._request("DELETE", f"annotations({annotation_id})")

    def dedupe_case_notes(self, case_id: str, subject: str) -> int:
        """Self-healing backstop: keep only the OLDEST note with this subject on
        the case and delete any extras. Deterministic (oldest createdon, then
        smallest id), so concurrent callers all keep the same one. Returns the
        number deleted. Never raises -- best effort."""
        subj = subject.replace("'", "''")
        params = urllib.parse.urlencode({
            "$select": "annotationid",
            "$filter": f"_objectid_value eq {case_id} and subject eq '{subj}'",
            "$orderby": "createdon asc,annotationid asc",
        })
        try:
            rows = (self._request("GET", "annotations?" + params) or {}).get("value", [])
        except Exception:
            return 0
        deleted = 0
        for r in rows[1:]:                             # keep rows[0] (oldest), drop the rest
            try:
                self.delete_note(r["annotationid"]); deleted += 1
            except Exception:
                pass
        return deleted

    # -- queues -------------------------------------------------------------
    def get_queue_id(self, name: str) -> Optional[str]:
        """Look up a Queue's id by its exact Name (e.g. 'Software Queue')."""
        n = name.replace("'", "''")
        params = urllib.parse.urlencode({
            "$select": "queueid", "$top": "1", "$filter": f"name eq '{n}'",
        })
        rows = (self._request("GET", "queues?" + params) or {}).get("value", [])
        return rows[0]["queueid"] if rows else None

    def set_case_queue(self, case_id: str, queue_id: str) -> None:
        """Move a Case into a queue. Incidents have no direct queue lookup field
        -- Dataverse tracks queue membership via a queueitem row, created by the
        bound AddToQueue action on the queue itself."""
        body = {"Target": {"@odata.type": "Microsoft.Dynamics.CRM.incident", "incidentid": case_id}}
        self._request("POST", f"queues({queue_id})/Microsoft.Dynamics.CRM.AddToQueue", body)

    def close_incident(self, case_id: str, subject: str, text: str = "",
                       status: int = 5) -> bool:
        """Resolve + close a Case via the CloseIncident action. Used to seed the
        similarity corpus with RESOLVED cases (see scripts/import_github_issues.py).
        Creates the incidentresolution activity and flips the Case to Resolved
        (statecode 1). status 5 = 'Problem Solved'.

        Returns True on success, False if the Case is already resolved (so a
        race can't create a second resolution). Raises on hard failure.
        """
        try:                                           # skip if already resolved
            cur = self._request("GET", f"incidents({case_id})?$select=statecode")
            if cur and cur.get("statecode") == 1:
                return False
        except Exception:
            pass
        body = {
            "IncidentResolution": {
                "subject": subject,
                "description": text,
                "incidentid@odata.bind": f"/incidents({case_id})",
            },
            "Status": status,
        }
        self._request("POST", "CloseIncident", body)
        return True
