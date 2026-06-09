"""
Adds the icm_ai_summary formatter to the DEFAULT incident form view.
Run from backend/:
    python -m servicenow_sync.add_icm_to_default_view
"""
import json
import requests
from . import config

SN   = config.SERVICENOW_INSTANCE_URL
AUTH = (config.SERVICENOW_USERNAME, config.SERVICENOW_PASSWORD)
H    = {"Accept": "application/json"}
HJ   = {"Content-Type": "application/json", "Accept": "application/json"}

FORMATTER_NAME = "icm_ai_summary.xml"


def get(table, query, fields="sys_id,name", limit=50):
    r = requests.get(f"{SN}/api/now/table/{table}", auth=AUTH, headers=H,
        params={"sysparm_query": query, "sysparm_fields": fields,
                "sysparm_display_value": "true", "sysparm_limit": limit},
        timeout=30)
    r.raise_for_status()
    return r.json().get("result", [])


def post(table, payload):
    r = requests.post(f"{SN}/api/now/table/{table}",
        auth=AUTH, headers=HJ, data=json.dumps(payload), timeout=30)
    r.raise_for_status()
    return r.json().get("result", {})


def patch(table, sid, payload):
    r = requests.patch(f"{SN}/api/now/table/{table}/{sid}",
        auth=AUTH, headers=HJ, data=json.dumps(payload), timeout=30)
    r.raise_for_status()
    return r.json().get("result", {})


def delete_rec(table, sid):
    requests.delete(f"{SN}/api/now/table/{table}/{sid}",
        auth=AUTH, headers=H, timeout=30)


def add_formatter_to_section(section_id, label=""):
    # Remove existing IcM formatter in this section (no duplicates)
    existing = get("sys_ui_element",
        f"sys_ui_section={section_id}^element={FORMATTER_NAME}",
        "sys_id", 5)
    for el in existing:
        delete_rec("sys_ui_element", el["sys_id"])
        print(f"    Removed old IcM element")

    # Shift all elements down by 2 to make room at top
    all_els = get("sys_ui_element", f"sys_ui_section={section_id}",
                  "sys_id,position", 60)
    for el in all_els:
        try:
            patch("sys_ui_element", el["sys_id"],
                  {"position": str(int(el.get("position") or 0) + 2)})
        except Exception:
            pass

    # Insert at position 0
    el = post("sys_ui_element", {
        "name":           "incident",
        "sys_ui_section": section_id,
        "element":        FORMATTER_NAME,
        "type":           "formatter",
        "position":       "0",
        "size_x":         "2",
        "size_y":         "1",
    })
    print(f"    [{label}] IcM formatter added at top: {el.get('sys_id')}")


def run():
    # ── Step 1: Find the Default view sys_id ─────────────────────────────────
    print("Finding views...")
    views = get("sys_ui_view", "name=Default^ORname=^ORname=incident",
                "sys_id,name,title", 10)
    print("Views found:")
    for v in views:
        print(f"  sys_id={v['sys_id']}  name='{v.get('name')}'  title={v.get('title')}")

    default_view_id = None
    for v in views:
        if v.get("name", "").lower() in ("", "default"):
            default_view_id = v["sys_id"]
            print(f"\nDefault view sys_id: {default_view_id}")
            break

    # ── Step 2: Find sections for the incident table in Default view ──────────
    print("\nFinding incident form sections...")
    target_sections = []

    if default_view_id:
        secs = get("sys_ui_section",
            f"name=incident^sys_view={default_view_id}",
            "sys_id,name,title,sys_view", 20)
        print(f"  Sections in Default view: {len(secs)}")
        for s in secs:
            print(f"    {s['sys_id']}  title={s.get('title')}")
        target_sections = secs

    # Also always include these well-known incident sections
    known = [
        ("6091af29c611227500b81eaaf2e05535", "known-default-header"),
        ("4fc4979ec0a8016401e142a5a0c599ce", "self-service"),
    ]
    for kid, label in known:
        if not any(s["sys_id"] == kid for s in target_sections):
            target_sections.append({"sys_id": kid, "_label": label})

    # ── Step 3: Add formatter to all target sections ──────────────────────────
    print(f"\nAdding IcM formatter to {len(target_sections)} section(s)...")
    for s in target_sections:
        sid = s["sys_id"]
        label = s.get("_label") or s.get("title") or sid[:8]
        print(f"  Section {sid} ({label}):")
        try:
            add_formatter_to_section(sid, label)
        except Exception as e:
            print(f"    ERROR: {e}")

    print("\n" + "=" * 60)
    print("DONE!")
    print()
    print("Steps to see the IcM panel:")
    print("  1. Go to ServiceNow > open INC0010658")
    print("  2. Press Ctrl + Shift + R  (hard-refresh, clears form cache)")
    print("  3. Scroll to the TOP of the form")
    print("  4. The IcM 'AI summary by IcM Assistant' panel is there")


if __name__ == "__main__":
    run()
