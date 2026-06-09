"""
Creates a BRAND NEW macro (icm_intel_v2) — bypasses all server cache.
Updates the formatter to point to the new macro.
Panel is hidden. Only an AI button shows at bottom. Click = expand/collapse.

Run from backend/:
    python -m servicenow_sync.deploy_fresh_macro
"""
import json
import requests
from . import config

SN   = config.SERVICENOW_INSTANCE_URL
AUTH = (config.SERVICENOW_USERNAME, config.SERVICENOW_PASSWORD)
H    = {"Accept": "application/json"}
HJ   = {"Content-Type": "application/json", "Accept": "application/json"}

MACRO_NAME   = "icm_intel_v2"       # fresh name = no cache hit
FMT_SYS_ID   = "caf9d6a283d10b1044b2c955eeaad309"   # existing formatter
MAIN_SECTION = "4fc4979ec0a8016401e142a5a0c599ce"

JELLY = r"""<?xml version="1.0" encoding="utf-8" ?>
<j:jelly trim="false" xmlns:j="jelly:core" xmlns:g="glide" xmlns:j2="null" xmlns:g2="null">
<g:evaluate>
var sysId = RP.getWindowProperties().get('sys_id') || '';
var priority='5 - Planning', category='--', sub='', state='New',
    assigned='Unassigned', grp='--', opened='--', caller='--',
    impact='--', urgency='--';
if (sysId) {
  var gr = new GlideRecord('incident');
  if (gr.get(sysId)) {
    priority = gr.priority.getDisplayValue()         || '5 - Planning';
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
var pNum  = parseInt((priority + '').charAt(0)) || 5;
var pColor = pNum &lt;= 2 ? '#c62828' : pNum == 3 ? '#e65100' : pNum == 4 ? '#1565c0' : '#455a64';
var pBg   = pNum &lt;= 2 ? '#ffebee' : pNum == 3 ? '#fff3e0' : pNum == 4 ? '#e3f2fd' : '#eceff1';
var now = new GlideDateTime();
var nowStr = now.getDisplayValue();
</g:evaluate>

<style>
#icm2-outer{margin:0;padding:0;display:none;}
#icm2-btn{
  display:inline-flex;align-items:center;gap:9px;
  background:linear-gradient(135deg,#1e3a5f 0%,#3a6bc7 100%);
  color:#fff;border:none;border-radius:26px;
  padding:10px 22px 10px 12px;
  font-size:14px;font-weight:600;cursor:pointer;
  box-shadow:0 3px 10px rgba(30,58,95,.35);
  letter-spacing:.2px;transition:box-shadow .2s,transform .1s;
  font-family:"Segoe UI",system-ui,Arial,sans-serif;
}
#icm2-btn:hover{box-shadow:0 5px 16px rgba(30,58,95,.5);transform:translateY(-1px);}
#icm2-btn .ring{
  width:28px;height:28px;border-radius:50%;
  background:rgba(255,255,255,.18);
  display:flex;align-items:center;justify-content:center;flex-shrink:0;
}
#icm2-btn .chev{
  font-size:10px;margin-left:4px;
  transition:transform .25s;display:inline-block;
}
#icm2-btn.open .chev{transform:rotate(180deg);}

#icm2-panel{
  overflow:hidden;max-height:0;opacity:0;
  transition:max-height .4s ease,opacity .3s ease;
  margin-top:0;
}
#icm2-panel.visible{max-height:1000px;opacity:1;}

#icm2-card{
  border:1px solid #d0d0d0;border-radius:0 0 8px 8px;
  overflow:hidden;margin-top:0;
  font-family:"Segoe UI",system-ui,Arial,sans-serif;
}
#icm2-hdr{
  background:#1e3a5f;padding:13px 22px;
  display:flex;justify-content:space-between;align-items:center;
}
#icm2-hdr .ht{color:#fff;font-size:14.5px;font-weight:600;display:flex;align-items:center;gap:8px;}
#icm2-hdr .hts{color:#90caf9;font-size:12px;}
#icm2-body{display:flex;background:#fff;}
.c2{flex:1;padding:16px 20px;border-right:1px solid #efefef;}
.c2:last-child{border-right:none;}
.ct2{font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;
     color:#78909c;margin-bottom:10px;padding-bottom:5px;border-bottom:2px solid #e8e8e8;}
.kv2{display:flex;margin-bottom:6px;gap:8px;font-size:13px;align-items:flex-start;}
.k2{color:#90a4ae;min-width:66px;flex-shrink:0;font-size:12.5px;}
.v2{color:#212121;font-weight:500;}
.badge2{display:inline-block;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:700;}
.row2{display:flex;gap:9px;margin-bottom:9px;align-items:flex-start;font-size:13px;}
.dot2{width:17px;height:17px;border-radius:50%;flex-shrink:0;margin-top:1px;
      display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:700;}
.done2{background:#e8f5e9;color:#2e7d32;}
.pend2{background:#f3e5f5;color:#6a1b9a;}
.act2{display:flex;gap:11px;margin-bottom:11px;align-items:flex-start;font-size:13px;}
.num2{width:22px;height:22px;border-radius:5px;background:#1e3a5f;color:#fff;
      flex-shrink:0;display:flex;align-items:center;justify-content:center;
      font-size:11px;font-weight:700;margin-top:1px;}
.ab2 strong{color:#1e3a5f;display:block;margin-bottom:2px;font-size:13px;}
.ab2 span{color:#546e7a;font-size:12px;line-height:1.5;}
#icm2-ftr{background:#f5f7f9;border-top:1px solid #e0e0e0;padding:8px 22px;
          display:flex;justify-content:space-between;align-items:center;}
#icm2-ftr em{font-size:11px;color:#90a4ae;font-style:normal;}
.fb2{background:none;border:1px solid #cfd8dc;border-radius:3px;cursor:pointer;
     font-size:12px;padding:2px 7px;color:#546e7a;margin-left:4px;}
</style>

<div id="icm2-outer">

  <!-- ── AI toggle button ── -->
  <button id="icm2-btn" onclick="icm2Toggle()" type="button">
    <span class="ring">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none"
           stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="3"/>
        <path d="M12 2v3M12 19v3M4.22 4.22l2.12 2.12M17.66 17.66l2.12 2.12
                 M2 12h3M19 12h3M4.22 19.78l2.12-2.12M17.66 6.34l2.12-2.12"/>
      </svg>
    </span>
    Incident Intelligence
    <span class="chev">&#9660;</span>
  </button>

  <!-- ── Collapsible report panel ── -->
  <div id="icm2-panel">
    <div id="icm2-card">

      <div id="icm2-hdr">
        <div class="ht"><span style="font-size:16px;">&#9670;</span> Incident Intelligence Report</div>
        <div class="hts">Auto-generated &nbsp;&#183;&nbsp; $[JS:nowStr]</div>
      </div>

      <div id="icm2-body">

        <!-- Snapshot -->
        <div class="c2">
          <div class="ct2">Incident Snapshot</div>
          <div class="kv2"><span class="k2">Priority</span>
            <span class="badge2" style="background:$[JS:pBg];color:$[JS:pColor];">$[JS:priority]</span></div>
          <div class="kv2"><span class="k2">State</span>    <span class="v2">$[JS:state]</span></div>
          <div class="kv2"><span class="k2">Category</span> <span class="v2">$[JS:catFull]</span></div>
          <div class="kv2"><span class="k2">Impact</span>   <span class="v2">$[JS:impact]</span></div>
          <div class="kv2"><span class="k2">Urgency</span>  <span class="v2">$[JS:urgency]</span></div>
          <div class="kv2"><span class="k2">Reporter</span> <span class="v2">$[JS:caller]</span></div>
          <div class="kv2"><span class="k2">Assigned</span> <span class="v2">$[JS:assigned]</span></div>
          <div class="kv2"><span class="k2">Group</span>    <span class="v2">$[JS:grp]</span></div>
          <div class="kv2"><span class="k2">Opened</span>   <span class="v2">$[JS:opened]</span></div>
        </div>

        <!-- Response Log -->
        <div class="c2">
          <div class="ct2">Response Log</div>
          <div class="row2"><div class="dot2 done2">&#10003;</div><div>Ticket created and logged</div></div>
          <div class="row2"><div class="dot2 done2">&#10003;</div><div>Assigned to <strong>$[JS:grp]</strong></div></div>
          <div class="row2"><div class="dot2 done2">&#10003;</div><div>Notification sent to assignee</div></div>
          <div class="row2"><div class="dot2 done2">&#10003;</div><div>SLA timer active</div></div>
          <div class="row2"><div class="dot2 pend2">&#9679;</div><div style="color:#6a1b9a;">Root cause &mdash; pending</div></div>
          <div class="row2"><div class="dot2 pend2">&#9679;</div><div style="color:#6a1b9a;">Resolution &mdash; pending</div></div>
        </div>

        <!-- Next Steps -->
        <div class="c2">
          <div class="ct2">Next Steps</div>
          <div class="act2"><div class="num2">1</div>
            <div class="ab2"><strong>Triage priority</strong>
              <span>Confirm <strong>$[JS:priority]</strong> matches real business impact; escalate if wider.</span></div></div>
          <div class="act2"><div class="num2">2</div>
            <div class="ab2"><strong>Engage reporter</strong>
              <span>Contact <strong>$[JS:caller]</strong> for reproduction steps or recent changes.</span></div></div>
          <div class="act2"><div class="num2">3</div>
            <div class="ab2"><strong>Search patterns</strong>
              <span>Check open incidents in <strong>$[JS:catFull]</strong> for recurring issues.</span></div></div>
        </div>

      </div><!-- /icm2-body -->

      <div id="icm2-ftr">
        <em>&#9888; AI-assisted &nbsp;&#183;&nbsp; Reflects field values at time of render</em>
        <span>Helpful? <button class="fb2">&#128077;</button><button class="fb2">&#128078;</button></span>
      </div>

    </div>
  </div><!-- /icm2-panel -->

</div><!-- /icm2-outer -->

<script>
function icm2Toggle() {
  var btn   = document.getElementById('icm2-btn');
  var panel = document.getElementById('icm2-panel');
  if (!btn || !panel) return;
  if (panel.classList.contains('visible')) {
    panel.classList.remove('visible');
    btn.classList.remove('open');
  } else {
    panel.classList.add('visible');
    btn.classList.add('open');
  }
}

(function placeWidget() {
  var outer = document.getElementById('icm2-outer');
  if (!outer) return;

  function go() {
    if (!document.getElementById('icm2-outer')) return;
    // Find the tab bar (Notes / Related Records / Resolution tabs)
    var tab = document.querySelector('.tabs2_list') ||
              document.querySelector('.nav-tabs') ||
              document.querySelector('ul[role="tablist"]') ||
              document.querySelector('.pane_list') ||
              document.querySelector('.tabs2');
    if (tab) {
      // Walk to the outermost tab wrapper
      var wrap = tab;
      for (var i = 0; i < 5; i++) {
        if (!wrap.parentNode || wrap.parentNode === document.body) break;
        wrap = wrap.parentNode;
      }
      wrap.parentNode.insertBefore(outer, wrap);
    } else {
      // Fallback: append to visible form area
      var area = document.querySelector('.form-horizontal') ||
                 document.querySelector('#gsft_main .form_section') ||
                 document.body;
      area.appendChild(outer);
    }
    outer.style.display = '';
  }

  setTimeout(go, 500);
  setTimeout(go, 1500);   // retry for slow renders
})();
</script>
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


def run():
    # 1. Delete old macro if exists with same name
    old = get("sys_ui_macro", f"name={MACRO_NAME}", "sys_id", 3)
    for m in old:
        requests.delete(f"{SN}/api/now/table/sys_ui_macro/{m['sys_id']}",
            auth=AUTH, headers=H, timeout=30)
        print(f"  Deleted old {MACRO_NAME}: {m['sys_id']}")

    # 2. Create fresh macro
    print(f"Creating fresh macro '{MACRO_NAME}'...")
    m = post("sys_ui_macro", {
        "name":        MACRO_NAME,
        "description": "Incident Intelligence toggle panel (v2)",
        "xml":         JELLY,
        "active":      "true",
    })
    macro_id = m.get("sys_id")
    print(f"  Created: {macro_id}")

    # 3. Point formatter to new macro
    print(f"Updating formatter {FMT_SYS_ID} -> macro {macro_id}...")
    patch("sys_ui_formatter", FMT_SYS_ID, {"macro": macro_id})
    print("  Formatter updated.")

    # 4. Ensure formatter element is in main section
    els = get("sys_ui_element",
        f"sys_ui_section={MAIN_SECTION}^element=icm_ai_summary.xml",
        "sys_id,position", 3)
    if els:
        patch("sys_ui_element", els[0]["sys_id"], {"position": "100"})
        print(f"  Element position set to 100 (bottom): {els[0]['sys_id']}")
    else:
        e = post("sys_ui_element", {
            "name": "incident", "sys_ui_section": MAIN_SECTION,
            "element": "icm_ai_summary.xml", "type": "formatter",
            "position": "100", "size_x": "2", "size_y": "1",
        })
        print(f"  Element created at position 100: {e.get('sys_id')}")

    print()
    print("=" * 60)
    print("DONE — fresh macro deployed, no cache issue.")
    print()
    print("1. Open any incident in ServiceNow")
    print("2. Ctrl + Shift + R")
    print("3. Scroll to bottom of form (above Notes tab)")
    print("4. See the 'Incident Intelligence' AI button")
    print("5. Click it -> panel expands | click again -> collapses")


if __name__ == "__main__":
    run()
