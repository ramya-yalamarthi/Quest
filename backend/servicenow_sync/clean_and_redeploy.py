"""
COMPLETE WIPE + FRESH DEPLOY
1. Deletes every icm-related macro, formatter, and element
2. Creates a brand-new section at the BOTTOM of the default incident form
3. Adds the toggle-button macro there
4. Panel stays hidden until the AI icon is clicked

Run from backend/:
    python -m servicenow_sync.clean_and_redeploy
"""
import json, requests
from . import config

SN   = config.SERVICENOW_INSTANCE_URL
AUTH = (config.SERVICENOW_USERNAME, config.SERVICENOW_PASSWORD)
H    = {"Accept": "application/json"}
HJ   = {"Content-Type": "application/json", "Accept": "application/json"}

DEFAULT_VIEW_ID = "a07bae06183232108bb255f46a373a6e"

# ── Fresh names (no cache conflict) ──────────────────────────────────────────
NEW_MACRO = "sn_incident_intel"
NEW_FMT   = "sn_incident_intel.xml"

JELLY = r"""<?xml version="1.0" encoding="utf-8" ?>
<j:jelly trim="false" xmlns:j="jelly:core" xmlns:g="glide" xmlns:j2="null" xmlns:g2="null">
<g:evaluate>
var sysId = RP.getWindowProperties().get('sys_id') || '';
var priority='--', category='--', sub='', state='--',
    assigned='Unassigned', grp='--', opened='--', caller='--',
    impact='--', urgency='--';
if (sysId) {
  var gr = new GlideRecord('incident');
  if (gr.get(sysId)) {
    priority = gr.priority.getDisplayValue()         || '--';
    category = gr.category.getDisplayValue()         || '--';
    sub      = gr.subcategory.getDisplayValue()      || '';
    state    = gr.state.getDisplayValue()            || '--';
    assigned = gr.assigned_to.getDisplayValue()      || 'Unassigned';
    grp      = gr.assignment_group.getDisplayValue() || '--';
    opened   = gr.opened_at.getDisplayValue()        || '--';
    caller   = gr.caller_id.getDisplayValue()        || '--';
    impact   = gr.impact.getDisplayValue()           || '--';
    urgency  = gr.urgency.getDisplayValue()          || '--';
  }
}
var catFull = category + (sub &amp;&amp; sub != '--' ? ' / ' + sub : '');
var pNum  = parseInt((priority + '').charAt(0)) || 5;
var pCol  = pNum &lt;= 2 ? '#c62828' : pNum == 3 ? '#e65100' : pNum == 4 ? '#1565c0' : '#455a64';
var pBg   = pNum &lt;= 2 ? '#ffebee' : pNum == 3 ? '#fff3e0' : pNum == 4 ? '#e3f2fd' : '#eceff1';
var ts = (new GlideDateTime()).getDisplayValue();
</g:evaluate>

<style>
#snii-btn {
  display: inline-flex; align-items: center; gap: 10px;
  background: linear-gradient(135deg, #1e3a5f, #3a6bc7);
  color: #fff; border: none; border-radius: 28px;
  padding: 11px 24px 11px 14px;
  font-size: 14px; font-weight: 600; cursor: pointer;
  box-shadow: 0 3px 12px rgba(30,58,95,.4);
  font-family: "Segoe UI", system-ui, Arial, sans-serif;
  transition: box-shadow .2s, transform .15s;
}
#snii-btn:hover { box-shadow: 0 6px 18px rgba(30,58,95,.55); transform: translateY(-1px); }
#snii-btn .snii-ring {
  width: 30px; height: 30px; border-radius: 50%;
  background: rgba(255,255,255,.2);
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
#snii-btn .snii-chev { font-size: 10px; margin-left: 4px; transition: transform .3s; display: inline-block; }
#snii-btn.open .snii-chev { transform: rotate(180deg); }

#snii-panel {
  overflow: hidden; max-height: 0; opacity: 0;
  transition: max-height .4s ease, opacity .3s ease;
}
#snii-panel.show { max-height: 1200px; opacity: 1; }

#snii-card {
  border: 1px solid #cfd8dc; border-radius: 0 6px 6px 6px;
  overflow: hidden; margin-top: 0;
  font-family: "Segoe UI", system-ui, Arial, sans-serif;
}
.snii-hdr {
  background: #1e3a5f; padding: 14px 22px;
  display: flex; justify-content: space-between; align-items: center;
}
.snii-hdr-t { color: #fff; font-size: 14.5px; font-weight: 600; display: flex; align-items: center; gap: 9px; }
.snii-hdr-ts { color: #90caf9; font-size: 12px; }
.snii-body { display: flex; background: #fff; }
.snii-col { flex: 1; padding: 16px 20px; border-right: 1px solid #eceff1; }
.snii-col:last-child { border-right: none; }
.snii-col-hd { font-size: 10px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase;
               color: #78909c; margin-bottom: 11px; padding-bottom: 5px; border-bottom: 2px solid #e8eaf6; }
.snii-row { display: flex; gap: 8px; margin-bottom: 7px; font-size: 13px; align-items: flex-start; }
.snii-k { color: #90a4ae; min-width: 68px; flex-shrink: 0; font-size: 12.5px; }
.snii-v { color: #212121; font-weight: 500; }
.snii-badge { display: inline-block; padding: 2px 11px; border-radius: 12px; font-size: 12px; font-weight: 700; }
.snii-log { display: flex; gap: 10px; margin-bottom: 9px; font-size: 13px; align-items: flex-start; }
.snii-dot { width: 18px; height: 18px; border-radius: 50%; flex-shrink: 0; margin-top: 1px;
            display: flex; align-items: center; justify-content: center; font-size: 9px; font-weight: 700; }
.snii-done { background: #e8f5e9; color: #2e7d32; }
.snii-pend { background: #f3e5f5; color: #6a1b9a; }
.snii-act { display: flex; gap: 12px; margin-bottom: 12px; font-size: 13px; align-items: flex-start; }
.snii-num { width: 23px; height: 23px; border-radius: 5px; background: #1e3a5f; color: #fff;
            flex-shrink: 0; display: flex; align-items: center; justify-content: center;
            font-size: 11px; font-weight: 700; margin-top: 1px; }
.snii-ab strong { color: #1e3a5f; display: block; margin-bottom: 2px; font-size: 13px; }
.snii-ab span { color: #546e7a; font-size: 12.5px; line-height: 1.55; }
.snii-ftr { background: #f5f7f9; border-top: 1px solid #e0e0e0; padding: 9px 22px;
            display: flex; justify-content: space-between; align-items: center; }
.snii-ftr em { font-size: 11.5px; color: #90a4ae; font-style: normal; }
.snii-fb { background: none; border: 1px solid #cfd8dc; border-radius: 4px;
           cursor: pointer; font-size: 13px; padding: 2px 8px; color: #546e7a; margin-left: 4px; }
</style>

<!-- AI toggle button -->
<button id="snii-btn" onclick="sniiToggle()" type="button">
  <span class="snii-ring">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
         stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 2C8 2 4 5 4 9c0 2.5 1.3 4.7 3.2 6L6 22l4-2h4l4 2-1.2-7C18.7 13.7 20 11.5 20 9c0-4-4-7-8-7z"/>
      <circle cx="9" cy="9" r="1" fill="#fff"/>
      <circle cx="15" cy="9" r="1" fill="#fff"/>
      <path d="M9 13s1 2 3 2 3-2 3-2"/>
    </svg>
  </span>
  Incident Intelligence
  <span class="snii-chev">&#9660;</span>
</button>

<!-- Collapsible panel -->
<div id="snii-panel">
  <div id="snii-card">

    <div class="snii-hdr">
      <div class="snii-hdr-t"><span style="font-size:17px;">&#9670;</span> Incident Intelligence Report</div>
      <div class="snii-hdr-ts">Auto-generated &nbsp;&#183;&nbsp; $[JS:ts]</div>
    </div>

    <div class="snii-body">

      <!-- Col 1: Snapshot -->
      <div class="snii-col">
        <div class="snii-col-hd">Incident Snapshot</div>
        <div class="snii-row"><span class="snii-k">Priority</span>
          <span class="snii-badge" style="background:$[JS:pBg];color:$[JS:pCol];">$[JS:priority]</span></div>
        <div class="snii-row"><span class="snii-k">State</span>    <span class="snii-v">$[JS:state]</span></div>
        <div class="snii-row"><span class="snii-k">Category</span> <span class="snii-v">$[JS:catFull]</span></div>
        <div class="snii-row"><span class="snii-k">Impact</span>   <span class="snii-v">$[JS:impact]</span></div>
        <div class="snii-row"><span class="snii-k">Urgency</span>  <span class="snii-v">$[JS:urgency]</span></div>
        <div class="snii-row"><span class="snii-k">Reporter</span> <span class="snii-v">$[JS:caller]</span></div>
        <div class="snii-row"><span class="snii-k">Assigned</span> <span class="snii-v">$[JS:assigned]</span></div>
        <div class="snii-row"><span class="snii-k">Group</span>    <span class="snii-v">$[JS:grp]</span></div>
        <div class="snii-row"><span class="snii-k">Opened</span>   <span class="snii-v">$[JS:opened]</span></div>
      </div>

      <!-- Col 2: Response Log -->
      <div class="snii-col">
        <div class="snii-col-hd">Response Log</div>
        <div class="snii-log"><div class="snii-dot snii-done">&#10003;</div><div>Ticket created and logged</div></div>
        <div class="snii-log"><div class="snii-dot snii-done">&#10003;</div><div>Assigned to <strong>$[JS:grp]</strong></div></div>
        <div class="snii-log"><div class="snii-dot snii-done">&#10003;</div><div>Notification sent to assignee</div></div>
        <div class="snii-log"><div class="snii-dot snii-done">&#10003;</div><div>SLA timer active</div></div>
        <div class="snii-log"><div class="snii-dot snii-pend">&#9679;</div><div style="color:#6a1b9a;">Root cause &mdash; pending</div></div>
        <div class="snii-log"><div class="snii-dot snii-pend">&#9679;</div><div style="color:#6a1b9a;">Resolution &mdash; pending</div></div>
      </div>

      <!-- Col 3: Next Steps -->
      <div class="snii-col">
        <div class="snii-col-hd">Next Steps</div>
        <div class="snii-act"><div class="snii-num">1</div>
          <div class="snii-ab"><strong>Triage priority</strong>
            <span>Confirm <strong>$[JS:priority]</strong> matches real impact; escalate if scope is wider than reported.</span></div></div>
        <div class="snii-act"><div class="snii-num">2</div>
          <div class="snii-ab"><strong>Engage reporter</strong>
            <span>Contact <strong>$[JS:caller]</strong> for reproduction steps or recent changes before the incident.</span></div></div>
        <div class="snii-act"><div class="snii-num">3</div>
          <div class="snii-ab"><strong>Search patterns</strong>
            <span>Look for open incidents in <strong>$[JS:catFull]</strong> with similar symptoms.</span></div></div>
      </div>

    </div>

    <div class="snii-ftr">
      <em>&#9888; AI-assisted &nbsp;&#183;&nbsp; Reflects field values at time of render</em>
      <span>Helpful?
        <button class="snii-fb">&#128077;</button>
        <button class="snii-fb">&#128078;</button>
      </span>
    </div>

  </div>
</div>

<script>
function sniiToggle() {
  var btn   = document.getElementById('snii-btn');
  var panel = document.getElementById('snii-panel');
  if (!btn || !panel) return;
  var open = panel.classList.contains('show');
  panel.classList[open ? 'remove' : 'add']('show');
  btn.classList[open ? 'remove' : 'add']('open');
}
</script>
</j:jelly>
"""


def get(table, query, fields="sys_id,name", limit=50):
    r = requests.get(f"{SN}/api/now/table/{table}", auth=AUTH, headers=H,
        params={"sysparm_query": query, "sysparm_fields": fields,
                "sysparm_display_value": "true", "sysparm_limit": limit}, timeout=30)
    return [] if r.status_code in (400, 403) else r.json().get("result", [])


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


def delete(table, sid):
    requests.delete(f"{SN}/api/now/table/{table}/{sid}",
        auth=AUTH, headers=H, timeout=30)


def run():
    # ── STEP 1: Delete all old icm/ir elements ──────────────────────────────
    print("Step 1: Removing ALL old icm/ir form elements...")
    for pattern in ["icm_ai_summary.xml", "icm_intel_v2.xml", "sn_incident_intel.xml"]:
        rows = get("sys_ui_element", f"element={pattern}^name=incident", "sys_id", 50)
        for r in rows:
            delete("sys_ui_element", r["sys_id"])
            print(f"  Deleted element: {r['sys_id']} ({pattern})")

    # ── STEP 2: Delete all old macros ───────────────────────────────────────
    print("\nStep 2: Removing all old icm/ir macros...")
    for name in ["icm_ai_summary", "icm_intel_v2", "sn_incident_intel"]:
        rows = get("sys_ui_macro", f"name={name}", "sys_id", 5)
        for r in rows:
            delete("sys_ui_macro", r["sys_id"])
            print(f"  Deleted macro: {name} ({r['sys_id']})")

    # ── STEP 3: Delete old formatters ───────────────────────────────────────
    print("\nStep 3: Removing old formatters...")
    for name in ["icm_ai_summary.xml", "icm_intel_v2.xml", "sn_incident_intel.xml"]:
        rows = get("sys_ui_formatter", f"name={name}", "sys_id", 5)
        for r in rows:
            delete("sys_ui_formatter", r["sys_id"])
            print(f"  Deleted formatter: {name} ({r['sys_id']})")

    # ── STEP 4: Create fresh macro ───────────────────────────────────────────
    print(f"\nStep 4: Creating fresh macro '{NEW_MACRO}'...")
    m = post("sys_ui_macro", {"name": NEW_MACRO, "xml": JELLY, "active": "true",
                               "description": "Incident Intelligence toggle panel"})
    macro_id = m["sys_id"]
    print(f"  Macro: {macro_id}")

    # ── STEP 5: Create fresh formatter ──────────────────────────────────────
    print(f"\nStep 5: Creating fresh formatter '{NEW_FMT}'...")
    f = post("sys_ui_formatter", {"name": NEW_FMT, "macro": macro_id, "sys_scope": "global"})
    fmt_id = f["sys_id"]
    print(f"  Formatter: {fmt_id}")

    # ── STEP 6: Create a new BOTTOM section for the incident form ────────────
    print("\nStep 6: Creating new bottom section for incident default view...")
    # Find the highest existing section position
    existing_secs = get("sys_ui_section",
        f"name=incident^sys_view={DEFAULT_VIEW_ID}",
        "sys_id,position", 50)
    max_pos = 0
    for s in existing_secs:
        try:
            p = int(s.get("position") or 0)
            if p > max_pos:
                max_pos = p
        except Exception:
            pass
    bottom_pos = max_pos + 100
    print(f"  Max existing position: {max_pos} → new section at {bottom_pos}")

    sec = post("sys_ui_section", {
        "name":     "incident",
        "sys_view": DEFAULT_VIEW_ID,
        "position": str(bottom_pos),
        "title":    "false",
    })
    sec_id = sec["sys_id"]
    print(f"  Bottom section created: {sec_id} (position={bottom_pos})")

    # ── STEP 7: Add formatter to bottom section ──────────────────────────────
    print("\nStep 7: Adding formatter to bottom section...")
    el = post("sys_ui_element", {
        "name":           "incident",
        "sys_ui_section": sec_id,
        "element":        NEW_FMT,
        "type":           "formatter",
        "position":       "0",
        "size_x":         "2",
        "size_y":         "1",
    })
    print(f"  Element added: {el['sys_id']}")

    print("\n" + "=" * 60)
    print("DONE — clean deploy complete.")
    print()
    print("In ServiceNow:")
    print("  1. Open any incident")
    print("  2. Ctrl + Shift + R")
    print("  3. Scroll to the BOTTOM of the form")
    print("  4. 'Incident Intelligence' AI button is there")
    print("  5. Click it -> report expands | click again -> collapses")


if __name__ == "__main__":
    run()
