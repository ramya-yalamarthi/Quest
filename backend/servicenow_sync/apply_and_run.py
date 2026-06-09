"""
Applies the New Employee Hire template to INC0010658 and starts the
Incident Support Workflow on it.

Run from backend/:
    python -m servicenow_sync.apply_and_run
"""
import json
import requests
from . import config

SN    = config.SERVICENOW_INSTANCE_URL
AUTH  = (config.SERVICENOW_USERNAME, config.SERVICENOW_PASSWORD)
H     = {"Accept": "application/json"}
HJ    = {"Content-Type": "application/json", "Accept": "application/json"}
WF_ID = "019056ae83510b1044b2c955eeaad321"


def get(table, query, fields="sys_id,name", limit=5):
    r = requests.get(f"{SN}/api/now/table/{table}", auth=AUTH, headers=H,
        params={"sysparm_query": query, "sysparm_fields": fields,
                "sysparm_display_value": "true", "sysparm_limit": limit},
        timeout=30)
    r.raise_for_status()
    return r.json().get("result", [])


def patch(table, sid, payload):
    r = requests.patch(f"{SN}/api/now/table/{table}/{sid}",
        auth=AUTH, headers=HJ, data=json.dumps(payload), timeout=30)
    r.raise_for_status()
    return r.json().get("result", {})


def display(val):
    if isinstance(val, dict):
        return val.get("display_value") or val.get("value", "")
    return str(val or "")


def run():
    # ── 1. Find INC0010658 ─────────────────────────────────────────────────
    rows = get("incident", "number=INC0010658",
               "sys_id,number,short_description,category,priority,"
               "assignment_group,state,wf_activity,description", 1)
    if not rows:
        print("Incident INC0010658 not found.")
        return
    inc = rows[0]
    iid = inc["sys_id"]
    print(f"Found INC0010658  sys_id = {iid}")
    print(f"  short_description = {display(inc.get('short_description'))}")
    print(f"  category          = {display(inc.get('category'))}")
    print(f"  priority          = {display(inc.get('priority'))}")
    print(f"  assignment_group  = {display(inc.get('assignment_group'))}")
    print(f"  state             = {display(inc.get('state'))}")
    print(f"  wf_activity       = {display(inc.get('wf_activity'))}")

    # ── 2. Apply New Employee Hire template fields ─────────────────────────
    print("\nApplying 'New Employee Hire' template fields...")
    updated = patch("incident", iid, {
        "category":         "request",
        "subcategory":      "new_employee",
        "priority":         "4",
        "urgency":          "3",
        "impact":           "3",
        "assignment_group": "IT",
        "description": (
            "New employee onboarding request. Please provision accounts, "
            "equipment and access as per the onboarding checklist."
        ),
        "state": "1",
    })
    print(f"  category         -> {display(updated.get('category'))}")
    print(f"  priority         -> {display(updated.get('priority'))}")
    print(f"  assignment_group -> {display(updated.get('assignment_group'))}")
    print(f"  description      -> set")

    # ── 3. Start Incident Support Workflow via Scripted REST ───────────────
    print("\nStarting 'Incident Support Workflow' on INC0010658...")
    wf_script = "\n".join([
        'var gr = new GlideRecord("incident");',
        'gr.get("' + iid + '");',
        'var wf = new Workflow();',
        'wf.startFlow("' + WF_ID + '", gr, "insert", {});',
        'gs.addInfoMessage("Workflow started on " + gr.number);',
    ])

    bg = requests.post(
        f"{SN}/api/now/v1/scripted_rest/background_script",
        auth=AUTH, headers=HJ,
        data=json.dumps({"script": wf_script}),
        timeout=30,
    )
    if bg.status_code in (200, 201):
        print(f"  Workflow start response: {bg.text[:200]}")
    else:
        # Try the sys_script_execution fallback
        print(f"  Background script returned {bg.status_code}, trying execute endpoint...")
        ex = requests.post(
            f"{SN}/api/now/table/sys_script_execution",
            auth=AUTH, headers=HJ,
            data=json.dumps({"script": wf_script}),
            timeout=30,
        )
        print(f"  Execute endpoint: {ex.status_code} {ex.text[:200]}")

    # ── 4. Print final state ───────────────────────────────────────────────
    final = get("incident", f"sys_id={iid}",
                "number,short_description,category,priority,urgency,"
                "assignment_group,state,wf_activity,description", 1)
    if final:
        print("\nFinal state of INC0010658:")
        for field in ["number", "short_description", "category", "priority",
                      "urgency", "assignment_group", "state", "wf_activity"]:
            print(f"  {field:22s} = {display(final[0].get(field))}")

    print("\n" + "="*60)
    print("Done.")
    print("Refresh INC0010658 in ServiceNow (Ctrl+Shift+R) to see:")
    print("  - Updated fields from the New Employee Hire template")
    print("  - Workflow activity field populated")
    print("  - Apply Template button in the '...' menu for future use")


if __name__ == "__main__":
    run()
