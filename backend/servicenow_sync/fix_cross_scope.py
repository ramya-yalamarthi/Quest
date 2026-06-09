"""
One-shot fix for:
  "Access to api 'setWorkflow' from scope 'x_1403612_css_cu_0' has been refused"

What it does (in order):
  1. Finds every Business Rule on the 'incident' table that lives in the CSS
     Customer support Incident scope (x_1403612_css_cu_0).
  2. Clears the 'wf_activity' (Run Workflow) field on each — that field is what
     triggers the cross-scope setWorkflow call.
  3. Moves each rule to Global scope so future workflow associations cannot
     re-introduce the same error.
  4. Creates a sys_scope_privilege entry that permanently allows the CSS scope
     to call setWorkflow on Global tables (belt-and-suspenders).

Run from the backend/ directory:
    python -m servicenow_sync.fix_cross_scope
"""

import json
import sys
import requests
from . import config

SN = config.SERVICENOW_INSTANCE_URL
AUTH = (config.SERVICENOW_USERNAME, config.SERVICENOW_PASSWORD)
HEADERS_JSON = {"Content-Type": "application/json", "Accept": "application/json"}
HEADERS_GET  = {"Accept": "application/json"}
CSS_SCOPE    = "x_1403612_css_cu_0"


def _get(path, params=None):
    r = requests.get(f"{SN}{path}", auth=AUTH, headers=HEADERS_GET, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("result", [])


def _patch(path, payload):
    r = requests.patch(f"{SN}{path}", auth=AUTH, headers=HEADERS_JSON,
                       data=json.dumps(payload), timeout=30)
    r.raise_for_status()
    return r.json().get("result", {})


def _post(path, payload):
    r = requests.post(f"{SN}{path}", auth=AUTH, headers=HEADERS_JSON,
                      data=json.dumps(payload), timeout=30)
    r.raise_for_status()
    return r.json().get("result", {})


# ── 1. Resolve the Global scope sys_id ────────────────────────────────────────
def get_global_scope_id():
    results = _get("/api/now/table/sys_scope",
                   {"sysparm_query": "scope=global", "sysparm_fields": "sys_id", "sysparm_limit": 1})
    if not results:
        print("ERROR: Could not find Global scope sys_id.")
        sys.exit(1)
    return results[0]["sys_id"]


# ── 2. Find all Business Rules in the CSS scope on the incident table ─────────
def find_css_business_rules():
    results = _get(
        "/api/now/table/sys_script",
        {
            "sysparm_query": f"sys_scope.scope={CSS_SCOPE}^collection=incident",
            "sysparm_fields": "sys_id,name,wf_activity,sys_scope",
            "sysparm_display_value": "true",
            "sysparm_limit": 50,
        },
    )
    return results


# ── 3. Clear wf_activity and move to Global scope ─────────────────────────────
def fix_business_rule(rule_sys_id, rule_name, global_scope_id):
    _patch(
        f"/api/now/table/sys_script/{rule_sys_id}",
        {
            "wf_activity": "",          # clear Run Workflow → no more setWorkflow call
            "sys_scope": global_scope_id,  # move to Global scope
        },
    )
    print(f"  Fixed rule: '{rule_name}' (sys_id={rule_sys_id})")


# ── 4. Grant permanent cross-scope privilege ──────────────────────────────────
def grant_cross_scope_privilege(global_scope_id):
    # Check if privilege already exists
    existing = _get(
        "/api/now/table/sys_scope_privilege",
        {
            "sysparm_query": (
                f"caller_scope.scope={CSS_SCOPE}"
                f"^privilege_type=script_include"
                f"^target_scope.sys_id={global_scope_id}"
                f"^name=Workflow"
            ),
            "sysparm_fields": "sys_id",
            "sysparm_limit": 1,
        },
    )
    if existing:
        print("  Cross-scope privilege already exists — skipping.")
        return

    # Get the CSS scope sys_id
    css_results = _get(
        "/api/now/table/sys_scope",
        {"sysparm_query": f"scope={CSS_SCOPE}", "sysparm_fields": "sys_id", "sysparm_limit": 1},
    )
    if not css_results:
        print("  WARNING: Could not find CSS scope record — skipping privilege grant.")
        return

    css_scope_id = css_results[0]["sys_id"]
    _post(
        "/api/now/table/sys_scope_privilege",
        {
            "caller_scope": css_scope_id,
            "target_scope": global_scope_id,
            "privilege_type": "script_include",
            "name": "Workflow",
            "status": "allowed",
        },
    )
    print("  Cross-scope privilege granted (CSS → Global / Workflow).")


# ── main ──────────────────────────────────────────────────────────────────────
def run():
    print(f"Connecting to {SN} as {AUTH[0]} …\n")

    print("Step 1: Resolving Global scope sys_id …")
    global_scope_id = get_global_scope_id()
    print(f"  Global scope sys_id = {global_scope_id}\n")

    print(f"Step 2: Finding Business Rules in scope '{CSS_SCOPE}' on incident table …")
    rules = find_css_business_rules()
    if not rules:
        print(f"  No Business Rules found in scope '{CSS_SCOPE}' — nothing to fix.\n")
    else:
        print(f"  Found {len(rules)} rule(s):\n")
        for rule in rules:
            name = rule.get("name", "<unnamed>")
            sys_id = rule.get("sys_id", "")
            wf = rule.get("wf_activity", {})
            wf_display = wf.get("display_value", "") if isinstance(wf, dict) else str(wf)
            print(f"  • {name} | wf_activity={wf_display or '(none)'}")
            fix_business_rule(sys_id, name, global_scope_id)
        print()

    print("Step 3: Granting permanent cross-scope access privilege …")
    grant_cross_scope_privilege(global_scope_id)
    print()

    print("Done. The setWorkflow cross-scope error should no longer appear.")
    print("Reload the ServiceNow Incidents page to confirm the banner is gone.")


if __name__ == "__main__":
    run()
