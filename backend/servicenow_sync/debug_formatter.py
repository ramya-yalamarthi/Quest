"""
Debug why the IcM formatter is not showing, and deploy it to the correct section.
Run from backend/:
    python -m servicenow_sync.debug_formatter
"""
import json
import requests
from . import config

SN   = config.SERVICENOW_INSTANCE_URL
AUTH = (config.SERVICENOW_USERNAME, config.SERVICENOW_PASSWORD)
H    = {"Accept": "application/json"}
HJ   = {"Content-Type": "application/json", "Accept": "application/json"}

MACRO_NAME = "icm_ai_summary"
FMT_NAME   = "icm_ai_summary.xml"

# Minimal test Jelly — no server-side scripting, just static HTML
TEST_JELLY = r"""<?xml version="1.0" encoding="utf-8" ?>
<j:jelly trim="false" xmlns:j="jelly:core" xmlns:g="glide" xmlns:j2="null" xmlns:g2="null">
<div style="background:#e8f5e9;border:2px solid #2e7d32;border-radius:6px;padding:16px;margin:8px 0;font-family:Segoe UI,Arial,sans-serif;">
  <strong style="color:#1b5e20;font-size:15px;">&#10022; AI summary by IcM Assistant — panel active</strong>
  <p style="color:#2e7d32;margin:6px 0 0;font-size:13px;">IcM template loaded successfully on this incident.</p>
</div>
</j:jelly>"""


def get(table, query, fields="sys_id,name", limit=20):
    r = requests.get(f"{SN}/api/now/table/{table}", auth=AUTH, headers=H,
        params={"sysparm_query": query, "sysparm_fields": fields,
                "sysparm_display_value": "true", "sysparm_limit": limit},
        timeout=30)
    if r.status_code in (400, 403):
        return []
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


def run():
    # ── 1. Update macro to simple test HTML ───────────────────────────────────
    print("Updating UI Macro to simple test HTML...")
    macs = get("sys_ui_macro", f"name={MACRO_NAME}", "sys_id,name,active", 1)
    if macs:
        patch("sys_ui_macro", macs[0]["sys_id"], {
            "xml":    TEST_JELLY,
            "active": "true",
        })
        print(f"  Macro updated: {macs[0]['sys_id']}")
    else:
        m = post("sys_ui_macro", {
            "name":    MACRO_NAME,
            "xml":     TEST_JELLY,
            "active":  "true",
        })
        print(f"  Macro created: {m.get('sys_id')}")

    # ── 2. Find formatter ─────────────────────────────────────────────────────
    fmts = get("sys_ui_formatter", f"name={FMT_NAME}", "sys_id,name,macro", 1)
    if not fmts:
        mac = get("sys_ui_macro", f"name={MACRO_NAME}", "sys_id", 1)
        mac_id = mac[0]["sys_id"] if mac else ""
        f = post("sys_ui_formatter", {
            "name":    FMT_NAME,
            "macro":   mac_id,
            "sys_scope": "global",
        })
        print(f"  Formatter created: {f.get('sys_id')}")
    else:
        print(f"  Formatter exists: {fmts[0]['sys_id']}")

    # ── 3. Find ALL sys_ui_element records for the incident form, Default view ─
    print("\nSearching for incident form elements (Default view)...")
    default_view = get("sys_ui_view", "name=Default^ORname=default",
                       "sys_id,name,title", 3)
    dv_id = default_view[0]["sys_id"] if default_view else None
    print(f"  Default view sys_id: {dv_id}")

    # Get all elements in ALL incident sections so we can find which one
    # has 'number' or 'caller_id' — that's the main header section
    all_sections = get("sys_ui_section",
        f"name=incident^sys_view={dv_id}" if dv_id else "name=incident",
        "sys_id,name,title", 50)
    print(f"  Found {len(all_sections)} sections in default view")

    # For each section, list its top 5 elements
    main_section_id = None
    for sec in all_sections:
        sid = sec["sys_id"]
        els = get("sys_ui_element",
            f"sys_ui_section={sid}",
            "sys_id,element,position,type", 10)
        field_names = [e.get("element","") for e in els if e.get("type") != "formatter"]
        if "number" in field_names or "caller_id" in field_names:
            print(f"\n  *** MAIN SECTION FOUND ***")
            print(f"      sys_id   = {sid}")
            print(f"      elements = {field_names[:8]}")
            main_section_id = sid
            break

    if not main_section_id:
        print("\n  number field not found in any section — trying all title=true sections")
        for sec in all_sections:
            if sec.get("title") == "true" or sec.get("title") is True:
                main_section_id = sec["sys_id"]
                print(f"  Using title section: {main_section_id}")
                break

    if not main_section_id and all_sections:
        main_section_id = all_sections[0]["sys_id"]
        print(f"  Fallback: using first section: {main_section_id}")

    # ── 4. Clean old formatter entries and add to main section ────────────────
    if main_section_id:
        print(f"\nCleaning old IcM formatter entries from all sections...")
        all_icm = get("sys_ui_element",
            f"element={FMT_NAME}^name=incident",
            "sys_id,sys_ui_section", 50)
        for e in all_icm:
            sec = e.get("sys_ui_section") or {}
            sec_id = sec.get("value") if isinstance(sec, dict) else str(sec or "")
            if sec_id != main_section_id:
                delete_rec("sys_ui_element", e["sys_id"])
                print(f"  Removed from other section: {e['sys_id']}")

        # Ensure it's in main section at position -1 (before all fields)
        in_main = [e for e in all_icm
                   if (e.get("sys_ui_section") or {}).get("value", "") == main_section_id
                   or str(e.get("sys_ui_section") or "") == main_section_id]
        if in_main:
            patch("sys_ui_element", in_main[0]["sys_id"], {"position": "-1"})
            print(f"  Kept in main section, set position=-1: {in_main[0]['sys_id']}")
        else:
            el = post("sys_ui_element", {
                "name":           "incident",
                "sys_ui_section": main_section_id,
                "element":        FMT_NAME,
                "type":           "formatter",
                "position":       "-1",
                "size_x":         "2",
                "size_y":         "1",
            })
            print(f"  Added to main section: {el.get('sys_id')}")

    print("\n" + "=" * 60)
    print("DONE. Now:")
    print("  1. Open INC0010658 in ServiceNow")
    print("  2. Press Ctrl + Shift + R")
    print("  3. If you see a GREEN box at the top: formatter works")
    print("     (then we replace the test HTML with the full IcM template)")
    print("  4. If still nothing: report back and we'll do it via Studio")


if __name__ == "__main__":
    run()
