"""
One-time fix for the demo corpus: the [fin] Finance reference Cases (seeded
by import_finance_issues.py) were all created within the same few days, so
the popup's incident-trend buckets (week/month/quarter) always showed identical
numbers -- there was no spread for the cumulative windows to differentiate.

Dataverse's `createdon` is read-only on Update (and `overriddencreatedon`
only takes effect at Create time), so the only way to backdate these records
is to delete and recreate them with a spread-out `overriddencreatedon`.

This reassigns each [fin] Case a random age (weighted so week < month <
quarter, growing realistically) and recreates it as a freshly resolved Case
with a new ticket number.

Usage:
    cd backend
    python3 scripts/spread_finance_dates.py
"""
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402
load_dotenv()

from app.orchestrator.dataverse import DataverseClient, available  # noqa: E402

TITLE_PREFIX = "[fin]"

# (min_days_ago, max_days_ago, weight) -- weighted so week < month < quarter
# cumulatively: ~15% land in the last week, ~35% in 8-29 days ago (month-only),
# ~50% in 31-89 days ago (quarter-only).
BUCKETS = [
    (1, 6, 0.15),
    (8, 29, 0.35),
    (31, 89, 0.50),
]


def random_created_on(now: datetime) -> str:
    r = random.random()
    cum = 0.0
    for lo, hi, w in BUCKETS:
        cum += w
        if r <= cum:
            days_ago = random.randint(lo, hi)
            seconds_jitter = random.randint(0, 86399)
            dt = now - timedelta(days=days_ago, seconds=-seconds_jitter)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv):
    limit = int(argv[1]) if len(argv) > 1 else None
    if not available():
        print("Dataverse env not set (DATAVERSE_URL / AZURE_*). Aborting.")
        return 1
    client = DataverseClient()

    customer = client.first_customer_bind()
    if not customer:
        print("No account/contact found to use as case customer. Aborting.")
        return 1
    key = "customerid_account@odata.bind" if "/accounts(" in customer \
        else "customerid_contact@odata.bind"

    # NOTE: startswith(title,'[fin]') is broken on this Dataverse instance --
    # the [ ] characters get passed through to the underlying SQL LIKE clause
    # unescaped, where they mean "match any single character in this set"
    # rather than literal brackets. contains() doesn't hit that path and was
    # verified to match exactly the [fin] Cases with zero false positives,
    # so use that instead.
    import urllib.parse
    params = {
        "$filter": "statecode eq 1 and contains(title,'fin')",
        "$select": "incidentid,title,description",
        "$top": "5000",
    }
    path = "incidents?" + urllib.parse.urlencode(params)
    data = client._request("GET", path) or {}
    cases = [c for c in data.get("value", []) if (c.get("title") or "").startswith(TITLE_PREFIX)]
    if limit:
        cases = cases[:limit]
    print(f"Found {len(cases)} resolved '{TITLE_PREFIX}' demo Cases to redate.\n")
    if not cases:
        return 0

    now = datetime.now(timezone.utc)
    ok, failed = 0, 0
    for n, c in enumerate(cases, 1):
        old_id = c["incidentid"]
        title = c.get("title") or "Untitled"
        desc = c.get("description") or ""
        created_on = random_created_on(now)
        try:
            client._request("DELETE", f"incidents({old_id})")
            body = {"title": title, "description": desc, key: customer,
                     "overriddencreatedon": created_on}
            resp = client._request("POST", "incidents", body,
                                    extra_headers={"Prefer": "return=representation"})
            new_id = (resp or {}).get("incidentid")
            if not new_id:
                print(f"  {n:>3}. FAIL (no id on create) {title[:60]}")
                failed += 1
                continue
            client.close_incident(new_id, subject="Resolution (backdated demo data)",
                                   text="Resolved (date redistributed for demo trend accuracy).")
            ok += 1
            print(f"  {n:>3}. OK   {created_on[:10]}  {title[:60]}")
        except Exception as exc:
            print(f"  {n:>3}. FAIL {title[:60]} :: {exc}")
            failed += 1
        time.sleep(0.3)

    print(f"\nDone. Redated {ok}/{len(cases)} Cases ({failed} failed).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
