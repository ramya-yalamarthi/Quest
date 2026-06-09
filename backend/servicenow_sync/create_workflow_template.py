"""
Creates transitions for the Incident Support Workflow,
a Business Rule to auto-start it on new incidents,
and a Template UI Action button on the incident form.

Run from backend/:
    python -m servicenow_sync.create_workflow_template
"""
import json
import requests
from . import config

SN   = config.SERVICENOW_INSTANCE_URL
AUTH = (config.SERVICENOW_USERNAME, config.SERVICENOW_PASSWORD)
H    = {"Accept": "application/json"}
HJ   = {"Content-Type": "application/json", "Accept": "application/json"}

WF_ID  = "019056ae83510b1044b2c955eeaad321"
WFV_ID = "d59056ae83510b1044b2c955eeaad329"


def get(table, query, fields="sys_id,name", limit=10):
    r = requests.get(f"{SN}/api/now/table/{table}", auth=AUTH, headers=H,
        params={"sysparm_query": query, "sysparm_fields": fields,
                "sysparm_display_value": "true", "sysparm_limit": limit}, timeout=30)
    r.raise_for_status()
    return r.json().get("result", [])


def post(table, payload):
    r = requests.post(f"{SN}/api/now/table/{table}", auth=AUTH,
        headers=HJ, data=json.dumps(payload), timeout=30)
    r.raise_for_status()
    return r.json().get("result", {})


def run():
    # ── 1. Wire transitions Begin -> Script -> End ─────────────────────────
    acts = get("wf_activity", f"workflow_version={WFV_ID}", "sys_id,name", 10)
    act_map = {a["name"]: a["sys_id"] for a in acts}
    print("Workflow activities:", list(act_map.keys()))

    transitions = [
        ("Begin",                  "Auto-Route by Category", "Yes"),
        ("Auto-Route by Category", "End",                    "Always"),
    ]
    print("\nCreating transitions...")
    for src_name, dst_name, cond in transitions:
        src = act_map.get(src_name)
        dst = act_map.get(dst_name)
        if src and dst:
            existing = get("wf_transition",
                f"workflow_version={WFV_ID}^from={src}^to={dst}", "sys_id", 1)
            if existing:
                print(f"  SKIP (exists): {src_name} -> {dst_name}")
            else:
                t = post("wf_transition", {
                    "workflow_version": WFV_ID,
                    "from": src,
                    "to": dst,
                    "name": cond,
                    "condition": "",
                })
                print(f"  CREATED: {src_name} -> {dst_name} ({t.get('sys_id')})")
        else:
            print(f"  MISSING activity: {src_name} or {dst_name}")

    # ── 2. Business Rule to start workflow on incident create ───────────────
    print("\nCreating Business Rule to start workflow on new incidents...")
    existing_br = get("sys_script",
        "name=Start Incident Support Workflow", "sys_id", 1)
    if existing_br:
        print("  Already exists.")
    else:
        script = (
            "(function executeRule(current, previous) {\n"
            "    var wf = new Workflow();\n"
            f'    wf.startFlow("{WF_ID}", current, "insert", ' + "{}" + ");\n"
            "})(current, previous);"
        )
        br = post("sys_script", {
            "name":          "Start Incident Support Workflow",
            "collection":    "incident",
            "when":          "after",
            "action_insert": "true",
            "action_update": "false",
            "advanced":      "true",
            "active":        "true",
            "sys_scope":     "global",
            "script":        script,
        })
        print(f"  CREATED: {br.get('sys_id')}")

    # ── 3. Template Apply UI Action on incident form ────────────────────────
    print("\nCreating Template UI Action on incident form...")
    existing_ui = get("sys_ui_action",
        "name=Apply Template^table=incident", "sys_id", 1)
    if existing_ui:
        print("  Already exists.")
    else:
        apply_script = (
            "var dialog = new GlideModal('template_picker');\n"
            "dialog.setTitle('Apply Template');\n"
            "dialog.setPreference('table', 'incident');\n"
            "dialog.render();"
        )
        ui = post("sys_ui_action", {
            "name":        "Apply Template",
            "table":       "incident",
            "action_name": "applyTemplate",
            "form_button": "true",
            "active":      "true",
            "hint":        "Apply a pre-filled template to this incident",
            "script":      apply_script,
        })
        print(f"  CREATED: {ui.get('sys_id')}")

    # ── 4. Verify templates exist ───────────────────────────────────────────
    print("\nVerifying templates...")
    tmpls = get("sys_template", "table=incident", "sys_id,name", 10)
    print(f"  Templates on incident table: {len(tmpls)}")
    for t in tmpls:
        print(f"    - {t.get('name')}")

    print("\n" + "="*60)
    print("DONE. In ServiceNow:")
    print("1. Hard-refresh the incident form: Ctrl+Shift+R")
    print("2. TEMPLATES: Click the '...' (More) button in the form header")
    print("   -> 'Apply Template' -> choose from the list")
    print("3. WORKFLOW: Go to All > Workflow > Workflow Editor")
    print("   -> search 'Incident Support Workflow' to view/edit it")
    print("4. The workflow auto-starts on every NEW incident created")


if __name__ == "__main__":
    run()
