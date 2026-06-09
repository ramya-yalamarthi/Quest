"""
Diagnostic: find every script in scope 'x_1403612_css_cu_0' that could be
triggering the cross-scope setWorkflow error, then fix them all.

Run from backend/:
    python -m servicenow_sync.diagnose_scope
"""
import json
import requests
from . import config

SN   = config.SERVICENOW_INSTANCE_URL
AUTH = (config.SERVICENOW_USERNAME, config.SERVICENOW_PASSWORD)
H    = {"Accept": "application/json"}
HJ   = {"Content-Type": "application/json", "Accept": "application/json"}
CSS  = "x_1403612_css_cu_0"


def get(table, query, fields, limit=50):
    r = requests.get(
        f"{SN}/api/now/table/{table}", auth=AUTH, headers=H,
        params={"sysparm_query": query, "sysparm_fields": fields,
                "sysparm_display_value": "true", "sysparm_limit": limit},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("result", [])


def patch(table, sys_id, payload):
    r = requests.patch(
        f"{SN}/api/now/table/{table}/{sys_id}", auth=AUTH, headers=HJ,
        data=json.dumps(payload), timeout=30,
    )
    r.raise_for_status()
    return r.json().get("result", {})


def get_global_id():
    rows = get("sys_scope", "scope=global", "sys_id", limit=1)
    return rows[0]["sys_id"] if rows else "global"


def section(label, rows, fix_fn=None):
    print(f"\n=== {label} ({len(rows)} found) ===")
    for row in rows:
        name = row.get("name", "<no name>")
        sid  = row.get("sys_id", "")
        sc   = row.get("script", "")
        if isinstance(sc, dict):
            sc = sc.get("value", "")
        wf   = row.get("wf_activity", {})
        wf_v = wf.get("display_value", "") if isinstance(wf, dict) else str(wf or "")
        has_wf_in_script = "setWorkflow" in (sc or "")
        print(f"  • {name}")
        print(f"    sys_id      = {sid}")
        print(f"    wf_activity = {wf_v or '(none)'}")
        print(f"    setWorkflow in script = {has_wf_in_script}")
        if fix_fn and (wf_v or has_wf_in_script):
            fix_fn(sid, name)


def run():
    global_id = get_global_id()
    print(f"Global scope sys_id = {global_id}")

    fixed = []

    def fix_business_rule(sid, name):
        patch("sys_script", sid, {
            "wf_activity":  "",
            "sys_scope":    global_id,
        })
        fixed.append(f"Business Rule: {name}")
        print(f"    → FIXED (cleared wf_activity, moved to Global)")

    def fix_ui_action(sid, name):
        patch("sys_ui_action", sid, {"sys_scope": global_id})
        fixed.append(f"UI Action: {name}")
        print(f"    → FIXED (moved to Global)")

    # 1. ALL business rules in CSS scope (any table)
    rows = get("sys_script",
               f"sys_scope.scope={CSS}",
               "sys_id,name,script,wf_activity,sys_scope")
    section("Business Rules — CSS scope (all tables)", rows, fix_business_rule)

    # 2. Business rules with setWorkflow anywhere
    rows2 = get("sys_script",
                "scriptLIKEsetWorkflow",
                "sys_id,name,script,wf_activity,sys_scope")
    section("Business Rules — contain 'setWorkflow' in script (any scope)", rows2)

    # 3. UI Actions in CSS scope
    rows3 = get("sys_ui_action",
                f"sys_scope.scope={CSS}",
                "sys_id,name,script,wf_activity,sys_scope,table")
    section("UI Actions — CSS scope", rows3, fix_ui_action)

    # 4. Script Includes in CSS scope
    rows4 = get("sys_script_include",
                f"sys_scope.scope={CSS}",
                "sys_id,name,script,sys_scope")
    section("Script Includes — CSS scope", rows4)
    for row in rows4:
        sc = row.get("script", "")
        if isinstance(sc, dict):
            sc = sc.get("value", "")
        if "setWorkflow" in (sc or ""):
            print(f"  *** setWorkflow found in Script Include '{row.get('name')}' ***")

    # 5. Client Scripts in CSS scope
    rows5 = get("sys_client_script",
                f"sys_scope.scope={CSS}",
                "sys_id,name,script,sys_scope,table")
    section("Client Scripts — CSS scope", rows5)

    # 6. Workflows in CSS scope
    rows6 = get("wf_workflow",
                f"sys_scope.scope={CSS}",
                "sys_id,name,sys_scope")
    section("Workflows — CSS scope", rows6)

    # 7. Check existing cross-scope privileges for CSS scope
    rows7 = get("sys_scope_privilege",
                f"caller_scope.scope={CSS}",
                "sys_id,name,status,privilege_type,caller_scope,target_scope")
    print(f"\n=== Existing cross-scope privileges for CSS scope ({len(rows7)} found) ===")
    for row in rows7:
        print(f"  • name={row.get('name')} | type={row.get('privilege_type')} "
              f"| status={row.get('status')} | target={row.get('target_scope',{}).get('display_value','?')}")

    print(f"\n{'─'*60}")
    if fixed:
        print(f"Fixed {len(fixed)} item(s):")
        for f in fixed:
            print(f"  ✓ {f}")
    else:
        print("No Business Rules or UI Actions needed fixing.")

    print("\nReload the ServiceNow Incidents page to verify the error is gone.")


if __name__ == "__main__":
    run()
