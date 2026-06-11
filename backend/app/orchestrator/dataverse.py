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
    def _request(self, method: str, path: str, body: Optional[dict] = None) -> Optional[dict]:
        url = f"{self.cfg['base']}/api/data/{API_VERSION}/{path.lstrip('/')}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self._get_token()}")
        req.add_header("Accept", "application/json")
        req.add_header("OData-MaxVersion", "4.0")
        req.add_header("OData-Version", "4.0")
        if body is not None:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            raw = r.read()
            return json.loads(raw) if raw else None

    # -- cases ------------------------------------------------------------
    def list_cases(self, top: int = 50, created_after: Optional[str] = None) -> list[dict]:
        """Return recent Cases as normalised dicts (newest first).

        created_after: ISO-8601 string; only cases created strictly after it.
        """
        params = {
            "$select": "incidentid,ticketnumber,title,description,prioritycode,statuscode,createdon",
            "$orderby": "createdon desc",
            "$top": str(top),
        }
        if created_after:
            params["$filter"] = f"createdon gt {created_after}"
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
            "created_on": c.get("createdon"),
        }

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
