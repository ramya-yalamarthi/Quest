"""
Moves the panel to BOTTOM of the incident form and replaces the design
with a completely new look (dark header, 3-column dashboard, badge-style priority).

Run from backend/:
    python -m servicenow_sync.redesign_icm_panel
"""
import json
import requests
from . import config

SN   = config.SERVICENOW_INSTANCE_URL
AUTH = (config.SERVICENOW_USERNAME, config.SERVICENOW_PASSWORD)
H    = {"Accept": "application/json"}
HJ   = {"Content-Type": "application/json", "Accept": "application/json"}

MACRO_NAME     = "icm_ai_summary"
FMT_NAME       = "icm_ai_summary.xml"
MAIN_SECTION   = "4fc4979ec0a8016401e142a5a0c599ce"

# ── Brand-new Jelly template — different from IcM ────────────────────────────
NEW_JELLY = r"""<?xml version="1.0" encoding="utf-8" ?>
<j:jelly trim="false" xmlns:j="jelly:core" xmlns:g="glide" xmlns:j2="null" xmlns:g2="null">
<g:evaluate>
var sysId = RP.getWindowProperties().get('sys_id') || '';
var priority='', category='', sub='', state='', assigned='', grp='',
    opened='', caller='', impact='', urgency='';
if (sysId) {
  var gr = new GlideRecord('incident');
  if (gr.get(sysId)) {
    priority = gr.priority.getDisplayValue()         || 'Not set';
    category = gr.category.getDisplayValue()         || '--';
    sub      = gr.subcategory.getDisplayValue()      || '';
    state    = gr.state.getDisplayValue()            || 'New';
    assigned = gr.assigned_to.getDisplayValue()      || 'Unassigned';
    grp      = gr.assignment_group.getDisplayValue() || '--';
    opened   = gr.opened_at.getDisplayValue()        || '--';
    caller   = gr.caller_id.getDisplayValue()        || '--';
    impact   = gr.impact.getDisplayValue()           || '--';
    urgency  = gr.urgency.getDisplayValue()          || '--';
  }
}
var catFull = category + (sub &amp;&amp; sub != '--' ? ' / ' + sub : '');
var pNum = parseInt(priority) || 5;
var pColor = pNum &lt;= 2 ? '#c62828' : pNum == 3 ? '#e65100' : pNum == 4 ? '#1565c0' : '#455a64';
var pBg    = pNum &lt;= 2 ? '#ffebee' : pNum == 3 ? '#fff3e0' : pNum == 4 ? '#e3f2fd' : '#eceff1';
var now = new GlideDateTime();
var nowStr = now.getDisplayValue();
</g:evaluate>

<style>
#ir-wrap *{box-sizing:border-box;font-family:"Segoe UI",system-ui,Arial,sans-serif;}
#ir-wrap{margin:24px 0 8px;border:1px solid #d0d0d0;border-radius:6px;overflow:hidden;}
#ir-header{background:#1e3a5f;padding:14px 20px;display:flex;justify-content:space-between;align-items:center;}
#ir-header .ir-title{color:#fff;font-size:15px;font-weight:600;display:flex;align-items:center;gap:8px;}
#ir-header .ir-ts{color:#90caf9;font-size:12px;}
#ir-body{display:flex;background:#fff;}
.ir-col{flex:1;padding:18px 20px;border-right:1px solid #e8e8e8;}
.ir-col:last-child{border-right:none;}
.ir-col-title{font-size:11px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;
              color:#78909c;margin-bottom:12px;padding-bottom:6px;border-bottom:2px solid #e0e0e0;}
.ir-kv{display:flex;align-items:flex-start;margin-bottom:8px;gap:8px;font-size:13px;}
.ir-k{color:#78909c;min-width:72px;flex-shrink:0;padding-top:1px;}
.ir-v{color:#212121;font-weight:500;}
.ir-badge{display:inline-block;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:700;}
.ir-step{display:flex;gap:10px;margin-bottom:10px;align-items:flex-start;font-size:13px;}
.ir-step-dot{width:18px;height:18px;border-radius:50%;flex-shrink:0;margin-top:1px;
             display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;}
.ir-step-done{background:#e8f5e9;color:#2e7d32;}
.ir-step-pending{background:#f3e5f5;color:#6a1b9a;}
.ir-action{display:flex;gap:12px;margin-bottom:12px;align-items:flex-start;font-size:13px;}
.ir-action-num{width:22px;height:22px;border-radius:4px;background:#1e3a5f;color:#fff;
               flex-shrink:0;display:flex;align-items:center;justify-content:center;
               font-size:11px;font-weight:700;margin-top:1px;}
.ir-action-body strong{color:#1e3a5f;display:block;margin-bottom:2px;font-size:13px;}
.ir-action-body span{color:#546e7a;font-size:12.5px;}
#ir-footer{background:#f5f7f9;border-top:1px solid #e0e0e0;padding:9px 20px;
           display:flex;justify-content:space-between;align-items:center;}
#ir-footer span{font-size:11.5px;color:#90a4ae;}
.ir-fb{background:none;border:1px solid #cfd8dc;border-radius:3px;cursor:pointer;
       font-size:13px;padding:2px 7px;color:#546e7a;margin-left:4px;}
</style>

<div id="ir-wrap">

  <!-- Header -->
  <div id="ir-header">
    <div class="ir-title">
      <span style="font-size:18px;">&#9670;</span>
      Incident Intelligence Report
    </div>
    <div class="ir-ts">Auto-generated &nbsp;&#183;&nbsp; $[JS:nowStr]</div>
  </div>

  <!-- Body: 3 columns -->
  <div id="ir-body">

    <!-- Col 1: Snapshot -->
    <div class="ir-col">
      <div class="ir-col-title">Incident Snapshot</div>

      <div class="ir-kv">
        <span class="ir-k">Priority</span>
        <span class="ir-badge" style="background:$[JS:pBg];color:$[JS:pColor];">$[JS:priority]</span>
      </div>
      <div class="ir-kv"><span class="ir-k">State</span>    <span class="ir-v">$[JS:state]</span></div>
      <div class="ir-kv"><span class="ir-k">Category</span> <span class="ir-v">$[JS:catFull]</span></div>
      <div class="ir-kv"><span class="ir-k">Impact</span>   <span class="ir-v">$[JS:impact]</span></div>
      <div class="ir-kv"><span class="ir-k">Urgency</span>  <span class="ir-v">$[JS:urgency]</span></div>
      <div class="ir-kv"><span class="ir-k">Reporter</span> <span class="ir-v">$[JS:caller]</span></div>
      <div class="ir-kv"><span class="ir-k">Assigned</span> <span class="ir-v">$[JS:assigned]</span></div>
      <div class="ir-kv"><span class="ir-k">Group</span>    <span class="ir-v">$[JS:grp]</span></div>
      <div class="ir-kv"><span class="ir-k">Opened</span>   <span class="ir-v">$[JS:opened]</span></div>
    </div>

    <!-- Col 2: Response Log -->
    <div class="ir-col">
      <div class="ir-col-title">Response Log</div>

      <div class="ir-step">
        <div class="ir-step-dot ir-step-done">&#10003;</div>
        <div>Ticket created and logged in the system</div>
      </div>
      <div class="ir-step">
        <div class="ir-step-dot ir-step-done">&#10003;</div>
        <div>Assigned to <strong>$[JS:grp]</strong></div>
      </div>
      <div class="ir-step">
        <div class="ir-step-dot ir-step-done">&#10003;</div>
        <div>Notification sent to assignee &amp; reporter</div>
      </div>
      <div class="ir-step">
        <div class="ir-step-dot ir-step-done">&#10003;</div>
        <div>SLA timer started &mdash; clock is running</div>
      </div>
      <div class="ir-step">
        <div class="ir-step-dot ir-step-pending">&#9679;</div>
        <div style="color:#6a1b9a;">Root cause analysis &mdash; pending</div>
      </div>
      <div class="ir-step">
        <div class="ir-step-dot ir-step-pending">&#9679;</div>
        <div style="color:#6a1b9a;">Resolution &mdash; pending</div>
      </div>
    </div>

    <!-- Col 3: Next Steps -->
    <div class="ir-col">
      <div class="ir-col-title">Next Steps</div>

      <div class="ir-action">
        <div class="ir-action-num">1</div>
        <div class="ir-action-body">
          <strong>Triage the priority</strong>
          <span>Confirm <strong>$[JS:priority]</strong> reflects real business impact. Escalate if the scope is wider than reported.</span>
        </div>
      </div>

      <div class="ir-action">
        <div class="ir-action-num">2</div>
        <div class="ir-action-body">
          <strong>Engage the reporter</strong>
          <span>Contact <strong>$[JS:caller]</strong> for reproduction steps, error logs, or any recent changes made before the incident.</span>
        </div>
      </div>

      <div class="ir-action">
        <div class="ir-action-num">3</div>
        <div class="ir-action-body">
          <strong>Search for patterns</strong>
          <span>Look for open or recently resolved incidents in <strong>$[JS:catFull]</strong> to spot recurring issues.</span>
        </div>
      </div>
    </div>

  </div><!-- /ir-body -->

  <!-- Footer -->
  <div id="ir-footer">
    <span>&#9888; AI-assisted &nbsp;&#183;&nbsp; Content reflects field data at time of render</span>
    <span>
      Helpful?
      <button class="ir-fb" title="Yes">&#128077;</button>
      <button class="ir-fb" title="No">&#128078;</button>
    </span>
  </div>

</div><!-- /ir-wrap -->
</j:jelly>
"""


def get(table, query, fields="sys_id,name", limit=5):
    r = requests.get(f"{SN}/api/now/table/{table}", auth=AUTH, headers=H,
        params={"sysparm_query": query, "sysparm_fields": fields,
                "sysparm_display_value": "true", "sysparm_limit": limit},
        timeout=30)
    if r.status_code in (400, 403):
        return []
    r.raise_for_status()
    return r.json().get("result", [])


def patch(table, sid, payload):
    r = requests.patch(f"{SN}/api/now/table/{table}/{sid}",
        auth=AUTH, headers=HJ, data=json.dumps(payload), timeout=30)
    r.raise_for_status()
    return r.json().get("result", {})


def run():
    # 1. Update macro with new design
    print("Updating UI Macro with new design...")
    macs = get("sys_ui_macro", f"name={MACRO_NAME}", "sys_id", 1)
    if macs:
        patch("sys_ui_macro", macs[0]["sys_id"], {"xml": NEW_JELLY})
        print(f"  Macro updated: {macs[0]['sys_id']}")

    # 2. Move formatter element to bottom (position 100)
    print("\nMoving formatter to bottom of section...")
    els = get("sys_ui_element",
        f"sys_ui_section={MAIN_SECTION}^element={FMT_NAME}",
        "sys_id,position", 3)
    for el in els:
        patch("sys_ui_element", el["sys_id"], {"position": "100"})
        print(f"  Set position=100: {el['sys_id']}")

    print("\n" + "=" * 60)
    print("DONE.")
    print()
    print("  1. Open any incident in ServiceNow")
    print("  2. Ctrl + Shift + R")
    print("  3. Scroll to BOTTOM of the form fields")
    print("  4. The Incident Intelligence Report panel appears")
    print()
    print("Panel shows:")
    print("  - Dark navy header with auto-generated timestamp")
    print("  - Left: Incident Snapshot (key-value with color-coded priority badge)")
    print("  - Middle: Response Log (checkmarks for done, purple for pending)")
    print("  - Right: Next Steps (numbered action cards)")


if __name__ == "__main__":
    run()
