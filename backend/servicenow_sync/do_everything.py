"""
Final all-in-one setup:
  1. Fix INC0010658 with correct template field values
  2. Patch the Business Rule to also fire on update (so workflow triggers)
  3. Trigger workflow by updating the incident
  4. Add Template bar formatter to Self Service view
  5. Print final state

Run from backend/:
    python -m servicenow_sync.do_everything
"""
import json
import requests
from . import config

SN    = config.SERVICENOW_INSTANCE_URL
AUTH  = (config.SERVICENOW_USERNAME, config.SERVICENOW_PASSWORD)
H     = {"Accept": "application/json"}
HJ    = {"Content-Type": "application/json", "Accept": "application/json"}

INC_NUMBER = "INC0010658"
WF_ID      = "019056ae83510b1044b2c955eeaad321"
WFV_ID     = "d59056ae83510b1044b2c955eeaad329"
SS_SECTION = "4fc4979ec0a8016401e142a5a0c599ce"


def get(table, query, fields="sys_id,name", limit=10):
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


def post(table, payload):
    r = requests.post(f"{SN}/api/now/table/{table}",
        auth=AUTH, headers=HJ, data=json.dumps(payload), timeout=30)
    r.raise_for_status()
    return r.json().get("result", {})


def dv(val):
    if isinstance(val, dict):
        return val.get("display_value") or val.get("value", "")
    return str(val or "")


def run():
    # ── 1. Get incident ────────────────────────────────────────────────────
    rows = get("incident", f"number={INC_NUMBER}",
               "sys_id,number,short_description,category,priority,"
               "urgency,assignment_group,state,wf_activity", 1)
    if not rows:
        print(f"{INC_NUMBER} not found.")
        return
    inc = rows[0]
    inc_id = inc["sys_id"]
    print(f"Incident: {INC_NUMBER}  sys_id={inc_id}")

    # ── 2. Find valid category choices ────────────────────────────────────
    cats = get("sys_choice",
        "name=incident^element=category^inactive=false",
        "sys_id,value,label", 30)
    print(f"\nAvailable categories ({len(cats)}):")
    for c in cats:
        print(f"  value={c.get('value'):20s} label={c.get('label')}")
    cat_value = next((c["value"] for c in cats
                      if "request" in c.get("label","").lower()
                      or "request" in c.get("value","").lower()), None)
    if not cat_value and cats:
        cat_value = cats[0]["value"]
    print(f"\nUsing category value: {cat_value}")

    # ── 3. Find Service Desk / Help Desk group ────────────────────────────
    groups = get("sys_user_group",
        "nameLIKEService Desk^ORnameLIKEHelp Desk^ORnameLIKEIT",
        "sys_id,name", 10)
    sd_group = next((g for g in groups
                     if "service desk" in g.get("name","").lower()), None)
    if not sd_group and groups:
        sd_group = groups[0]
    print(f"Using group: {sd_group.get('name')} ({sd_group.get('sys_id')})")

    # ── 4. Apply template fields to incident ──────────────────────────────
    print(f"\nApplying New Employee Hire template to {INC_NUMBER}...")
    update_payload = {
        "urgency":          "3",
        "impact":           "3",
        "priority":         "4",
        "description": (
            "New employee onboarding request. "
            "Please provision accounts, equipment and access "
            "as per the onboarding checklist."
        ),
        "state": "1",
    }
    if cat_value:
        update_payload["category"] = cat_value
    if sd_group:
        update_payload["assignment_group"] = sd_group["sys_id"]

    updated = patch("incident", inc_id, update_payload)
    print(f"  category         = {dv(updated.get('category'))}")
    print(f"  priority         = {dv(updated.get('priority'))}")
    print(f"  urgency          = {dv(updated.get('urgency'))}")
    print(f"  assignment_group = {dv(updated.get('assignment_group'))}")

    # ── 5. Patch Business Rule to also fire on update ─────────────────────
    print("\nPatching Business Rule to fire on insert AND update...")
    br_rows = get("sys_script",
        "name=Start Incident Support Workflow", "sys_id,name", 1)
    if br_rows:
        br_id = br_rows[0]["sys_id"]
        patch("sys_script", br_id, {
            "action_insert": "true",
            "action_update": "true",
        })
        print(f"  BR updated: {br_id}")

        # Trigger it by doing a dummy update (add a work note)
        print("  Triggering workflow via incident update...")
        patch("incident", inc_id, {
            "work_notes": "Workflow triggered by incident update."
        })
        print("  Update sent.")
    else:
        print("  Business Rule not found.")

    # ── 6. Add Template bar to Self Service view ──────────────────────────
    print("\nAdding template bar section to Self Service view...")
    existing = get("sys_ui_element",
        f"sys_ui_section={SS_SECTION}^element=sys_templates.xml",
        "sys_id", 1)
    if not existing:
        try:
            post("sys_ui_element", {
                "name":           "incident",
                "sys_ui_section": SS_SECTION,
                "element":        "sys_templates.xml",
                "type":           "formatter",
                "position":       "0",
            })
            print("  Template bar formatter added at position 0.")
        except Exception as e:
            print(f"  Template bar: {e}")
    else:
        print("  Template bar already present.")

    # ── 7. Final state ─────────────────────────────────────────────────────
    import time
    time.sleep(3)
    final = get("incident", f"sys_id={inc_id}",
                "number,short_description,category,priority,urgency,"
                "assignment_group,state,wf_activity,description", 1)
    if final:
        f = final[0]
        print(f"\nFinal state of {INC_NUMBER}:")
        for field in ["number", "short_description", "category", "priority",
                      "urgency", "assignment_group", "state", "wf_activity"]:
            print(f"  {field:22s} = {dv(f.get(field))}")

    print("\n" + "="*60)
    print("ALL DONE.")
    print(f"Refresh {INC_NUMBER} in ServiceNow (Ctrl+Shift+R).")
    print("Workflow:  All > Workflow > Workflow Editor > Incident Support Workflow")
    print("Templates: open any incident > '...' menu > Apply Template")


if __name__ == "__main__":
    run()
