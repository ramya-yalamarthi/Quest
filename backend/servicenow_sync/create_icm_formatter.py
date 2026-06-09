"""
Creates an IcM-style "AI summary" panel directly on the ServiceNow incident form.

What it builds:
  1. sys_ui_macro  — Jelly template that reads the incident and renders
                     the exact IcM layout (What we know / What has been done /
                     Recommended actions) using live incident field data.
  2. sys_ui_formatter — links the macro to a form element name.
  3. sys_ui_element  — adds the formatter at the TOP of the Self Service
                       incident form section (before all other fields).

Run from backend/:
    python -m servicenow_sync.create_icm_formatter
"""
import json
import requests
from . import config

SN   = config.SERVICENOW_INSTANCE_URL
AUTH = (config.SERVICENOW_USERNAME, config.SERVICENOW_PASSWORD)
H    = {"Accept": "application/json"}
HJ   = {"Content-Type": "application/json", "Accept": "application/json"}

# The Self Service view section on the incident form
SS_SECTION = "4fc4979ec0a8016401e142a5a0c599ce"

# ── Jelly template ────────────────────────────────────────────────────────────
# Uses server-side GlideRecord so no external call or auth is needed.
# Renders inline CSS + HTML in the exact IcM panel style.
JELLY = r"""<?xml version="1.0" encoding="utf-8" ?>
<j:jelly trim="false" xmlns:j="jelly:core" xmlns:g="glide" xmlns:j2="null" xmlns:g2="null">
<g:evaluate>
var sysId = RP.getWindowProperties().get('sys_id') || '';
var priority = '', category = '', state = '', assigned = '', grp = '',
    opened = '', caller = '', subcategory = '', impact = '', urgency = '';
if (sysId) {
  var gr = new GlideRecord('incident');
  if (gr.get(sysId)) {
    priority    = gr.priority.getDisplayValue()         || 'Not set';
    category    = gr.category.getDisplayValue()         || 'Not categorised';
    subcategory = gr.subcategory.getDisplayValue()      || '';
    state       = gr.state.getDisplayValue()            || 'New';
    assigned    = gr.assigned_to.getDisplayValue()      || 'Unassigned';
    grp         = gr.assignment_group.getDisplayValue() || 'Not assigned';
    opened      = gr.opened_at.getDisplayValue()        || 'N/A';
    caller      = gr.caller_id.getDisplayValue()        || 'Not specified';
    impact      = gr.impact.getDisplayValue()           || '';
    urgency     = gr.urgency.getDisplayValue()          || '';
  }
}
var catLine = category + (subcategory ? ' / ' + subcategory : '');
var now = new GlideDateTime();
var nowStr = now.getDisplayValue();
</g:evaluate>

<style>
  #icm-panel *{box-sizing:border-box;}
  #icm-panel{background:#fff;border:1px solid #e0e0e0;border-radius:4px;
             padding:20px 24px 14px;margin:14px 0 18px;
             font-family:"Segoe UI",system-ui,Arial,sans-serif;font-size:13.5px;}
  #icm-panel .icm-hdr{display:flex;align-items:center;gap:8px;margin-bottom:3px;}
  #icm-panel .icm-spark{font-size:17px;color:#5c6bc0;font-weight:700;}
  #icm-panel .icm-title{font-size:15px;font-weight:600;color:#1a1a1a;}
  #icm-panel .icm-ts{font-size:12px;color:#888;margin-bottom:14px;display:flex;align-items:center;gap:5px;}
  #icm-panel .icm-hr{border:none;border-top:1px solid #e8e8e8;margin:0 0 16px;}
  #icm-panel .icm-body{display:flex;gap:0;align-items:flex-start;}
  #icm-panel .icm-left{flex:0 0 62%;padding-right:32px;}
  #icm-panel .icm-div{width:1px;background:#e0e0e0;align-self:stretch;flex-shrink:0;}
  #icm-panel .icm-right{flex:0 0 38%;padding-left:28px;}
  #icm-panel .icm-section-hd{margin:0 0 8px;font-weight:700;font-size:14px;color:#1a1a1a;}
  #icm-panel .icm-list{margin:0 0 18px;padding-left:20px;line-height:1.8;}
  #icm-panel .icm-list li{margin-bottom:2px;}
  #icm-panel .icm-rec-hd{margin:0 0 10px;font-size:14px;font-weight:600;
                          border-bottom:1px dashed #aaa;padding-bottom:4px;display:inline-block;}
  #icm-panel .icm-rec-list{margin:0;padding-left:16px;line-height:1.8;}
  #icm-panel .icm-rec-list li{margin-bottom:10px;}
  #icm-panel .icm-footer{border-top:1px solid #e8e8e8;margin-top:14px;padding-top:10px;
                          display:flex;justify-content:space-between;align-items:center;}
  #icm-panel .icm-footer-l,.icm-footer-r{font-size:12px;color:#aaa;display:flex;align-items:center;gap:5px;}
</style>

<div id="icm-panel">
  <!-- Header -->
  <div class="icm-hdr">
    <span class="icm-spark">&#10022;</span>
    <span class="icm-title">AI summary by IcM Assistant</span>
  </div>

  <!-- Timestamp -->
  <div class="icm-ts">
    <span>&#8857;</span>
    <span>Last updated at $[JS:nowStr]</span>
  </div>

  <hr class="icm-hr"/>

  <!-- Two-column body -->
  <div class="icm-body">

    <!-- LEFT: What we know + What has been done -->
    <div class="icm-left">

      <p class="icm-section-hd">What we know:</p>
      <ul class="icm-list">
        <li><strong>Priority:</strong> $[JS:priority]</li>
        <li><strong>State:</strong> $[JS:state]</li>
        <li><strong>Category:</strong> $[JS:catLine]</li>
        <j:if test="${impact != ''}">
        <li><strong>Impact:</strong> $[JS:impact]</li>
        </j:if>
        <j:if test="${urgency != ''}">
        <li><strong>Urgency:</strong> $[JS:urgency]</li>
        </j:if>
        <li><strong>Reported by:</strong> $[JS:caller]</li>
        <li><strong>Assigned to:</strong> $[JS:assigned] &mdash; $[JS:grp]</li>
        <li><strong>Opened:</strong> $[JS:opened]</li>
      </ul>

      <p class="icm-section-hd">What has been done so far:</p>
      <ul class="icm-list" style="margin-bottom:0;">
        <li>Incident created and assigned to $[JS:grp]</li>
        <li>Automated notification workflow triggered &mdash; assignee alerted</li>
        <li>SLA timer started at $[JS:opened]</li>
        <li>Incident categorised as <strong>$[JS:catLine]</strong> with priority <strong>$[JS:priority]</strong></li>
      </ul>

    </div>

    <!-- Vertical divider -->
    <div class="icm-div"></div>

    <!-- RIGHT: Recommended actions -->
    <div class="icm-right">
      <p class="icm-rec-hd">Recommended actions</p>
      <ol class="icm-rec-list">
        <li>
          <strong>Verify priority:</strong> Confirm that priority <strong>$[JS:priority]</strong>
          matches actual business impact and escalate if needed.
        </li>
        <li>
          <strong>Contact reporter:</strong> Reach out to <strong>$[JS:caller]</strong>
          for additional context or steps to reproduce.
        </li>
        <li>
          <strong>Check similar incidents:</strong> Search open incidents in
          category <strong>$[JS:catLine]</strong> to identify recurring patterns.
        </li>
      </ol>
    </div>

  </div><!-- /icm-body -->

  <!-- Footer -->
  <div class="icm-footer">
    <div class="icm-footer-l">
      <span>AI-generated content may be incorrect</span>
      <span title="Helpful" style="cursor:pointer;">&#128077;</span>
      <span title="Not helpful" style="cursor:pointer;">&#128078;</span>
    </div>
    <div class="icm-footer-r">
      <span>Are these actions useful?</span>
      <span title="Yes" style="cursor:pointer;">&#128077;</span>
      <span title="No" style="cursor:pointer;">&#128078;</span>
    </div>
  </div>

</div><!-- /icm-panel -->
</j:jelly>
"""


def get(table, query, fields="sys_id,name", limit=5):
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
    r = requests.delete(f"{SN}/api/now/table/{table}/{sid}",
        auth=AUTH, headers=H, timeout=30)
    return r.status_code


MACRO_NAME     = "icm_ai_summary"
FORMATTER_NAME = "icm_ai_summary.xml"


def run():
    # ── 1. Create / update the UI Macro ──────────────────────────────────────
    print("Step 1: Creating UI Macro 'icm_ai_summary'...")
    existing = get("sys_ui_macro", f"name={MACRO_NAME}", "sys_id,name", 1)
    if existing:
        macro_id = existing[0]["sys_id"]
        patch("sys_ui_macro", macro_id, {"xml": JELLY})
        print(f"  Updated existing macro: {macro_id}")
    else:
        m = post("sys_ui_macro", {
            "name":        MACRO_NAME,
            "description": "IcM-style AI summary panel for incident form",
            "xml":         JELLY,
            "active":      "true",
        })
        macro_id = m.get("sys_id")
        print(f"  Created macro: {macro_id}")

    # ── 2. Create / update the UI Formatter ──────────────────────────────────
    print(f"\nStep 2: Creating UI Formatter '{FORMATTER_NAME}'...")
    existing_fmt = get("sys_ui_formatter", f"name={FORMATTER_NAME}", "sys_id,name", 1)
    if existing_fmt:
        fmt_id = existing_fmt[0]["sys_id"]
        patch("sys_ui_formatter", fmt_id, {"macro": macro_id})
        print(f"  Updated existing formatter: {fmt_id}")
    else:
        f = post("sys_ui_formatter", {
            "name":        FORMATTER_NAME,
            "macro":       macro_id,
            "sys_scope":   "global",
        })
        fmt_id = f.get("sys_id")
        print(f"  Created formatter: {fmt_id}")

    # ── 3. Add formatter to Self Service incident form (top position) ─────────
    print(f"\nStep 3: Adding formatter to Self Service incident form...")

    # Remove any existing icm element first (avoid duplicates)
    existing_el = get("sys_ui_element",
        f"sys_ui_section={SS_SECTION}^element={FORMATTER_NAME}",
        "sys_id", 5)
    for el in existing_el:
        code = delete_rec("sys_ui_element", el["sys_id"])
        print(f"  Removed old element: {el['sys_id']} (HTTP {code})")

    # Shift all existing elements down by 2 to make room at top
    all_els = get("sys_ui_element",
        f"sys_ui_section={SS_SECTION}",
        "sys_id,position,element", 50)
    print(f"  Found {len(all_els)} existing elements — shifting positions...")
    for el in all_els:
        try:
            pos = int(el.get("position") or 0)
            patch("sys_ui_element", el["sys_id"], {"position": str(pos + 2)})
        except Exception:
            pass

    # Insert at position 0
    el = post("sys_ui_element", {
        "name":           "incident",
        "sys_ui_section": SS_SECTION,
        "element":        FORMATTER_NAME,
        "type":           "formatter",
        "position":       "0",
        "size_x":         "2",
        "size_y":         "1",
    })
    print(f"  Inserted IcM formatter at position 0: {el.get('sys_id')}")

    print("\n" + "=" * 60)
    print("DONE!")
    print()
    print("To see the IcM panel in ServiceNow:")
    print("  1. Open any incident (e.g. INC0010658)")
    print("  2. Hard-refresh: Ctrl + Shift + R")
    print("  3. The 'AI summary by IcM Assistant' panel appears at the TOP")
    print("     of the form, above the form fields.")
    print()
    print("If it doesn't appear:")
    print("  → In ServiceNow: Admin > System UI > UI Macros > icm_ai_summary")
    print("    confirm the macro is Active.")
    print("  → Check the form view is 'Self Service (ess)'.")


if __name__ == "__main__":
    run()
