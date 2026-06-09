"""
Updates the Jelly macro so the panel is HIDDEN by default.
Only a small AI icon button appears at the bottom.
Clicking the icon expands / collapses the full panel.

Run from backend/:
    python -m servicenow_sync.icm_with_toggle
"""
import json
import requests
from . import config

SN   = config.SERVICENOW_INSTANCE_URL
AUTH = (config.SERVICENOW_USERNAME, config.SERVICENOW_PASSWORD)
H    = {"Accept": "application/json"}
HJ   = {"Content-Type": "application/json", "Accept": "application/json"}

MACRO_NAME = "icm_ai_summary"

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
var pBg    = pNum &lt;= 2 ? '#ffebee' : pNum == 3 ? '#fff3e0' : pNum == 4 ? '#e3f2fd' : '#eceff1';
var now = new GlideDateTime();
var nowStr = now.getDisplayValue();
</g:evaluate>

<style>
/* ── AI toggle button ─────────────────────────────────── */
#ir-ai-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: linear-gradient(135deg, #1e3a5f 0%, #2e5fa3 100%);
  color: #fff;
  border: none;
  border-radius: 24px;
  padding: 9px 20px 9px 14px;
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(30,58,95,.30);
  letter-spacing: .2px;
  transition: box-shadow .2s, transform .1s;
  font-family: "Segoe UI", system-ui, Arial, sans-serif;
}
#ir-ai-btn:hover { box-shadow: 0 4px 14px rgba(30,58,95,.45); transform: translateY(-1px); }
#ir-ai-btn .ir-icon-ring {
  width: 26px; height: 26px; border-radius: 50%;
  background: rgba(255,255,255,.18);
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; flex-shrink: 0;
}
#ir-ai-btn .ir-chevron {
  margin-left: 4px; font-size: 10px;
  transition: transform .25s;
  display: inline-block;
}
#ir-ai-btn.open .ir-chevron { transform: rotate(180deg); }

/* ── Expandable panel ─────────────────────────────────── */
#ir-intel-panel {
  overflow: hidden;
  max-height: 0;
  opacity: 0;
  transition: max-height .35s ease, opacity .25s ease;
  font-family: "Segoe UI", system-ui, Arial, sans-serif;
}
#ir-intel-panel.visible {
  max-height: 800px;
  opacity: 1;
}

/* ── Wrapper ─────────────────────────────────────────── */
#ir-wrap-outer {
  margin: 18px 0 12px;
  display: none;  /* JS moves into position then shows */
}

/* ── Inner panel styles ──────────────────────────────── */
#ir-intel-panel * { box-sizing: border-box; }
#ir-intel { border: 1px solid #d0d0d0; border-radius: 0 0 6px 6px; overflow: hidden; margin-top: 0; }
#ir-hdr { background: #1e3a5f; padding: 12px 20px; display: flex; justify-content: space-between; align-items: center; }
#ir-hdr .t { color: #fff; font-size: 14px; font-weight: 600; display: flex; align-items: center; gap: 7px; }
#ir-hdr .ts { color: #90caf9; font-size: 11.5px; }
#ir-body { display: flex; background: #fff; }
.ir-c { flex: 1; padding: 15px 20px; border-right: 1px solid #eee; }
.ir-c:last-child { border-right: none; }
.ir-ct { font-size: 10px; font-weight: 700; letter-spacing: .9px; text-transform: uppercase;
         color: #78909c; margin-bottom: 10px; padding-bottom: 5px; border-bottom: 2px solid #e8e8e8; }
.ir-kv { display: flex; margin-bottom: 6px; gap: 8px; font-size: 13px; align-items: flex-start; }
.ir-k  { color: #90a4ae; min-width: 66px; flex-shrink: 0; }
.ir-v  { color: #212121; font-weight: 500; }
.ir-badge { display: inline-block; padding: 1px 9px; border-radius: 10px; font-size: 12px; font-weight: 700; }
.ir-row { display: flex; gap: 9px; margin-bottom: 8px; align-items: flex-start; font-size: 13px; }
.ir-dot { width: 16px; height: 16px; border-radius: 50%; flex-shrink: 0; margin-top: 1px;
          display: flex; align-items: center; justify-content: center; font-size: 9px; font-weight: 700; }
.ir-done { background: #e8f5e9; color: #2e7d32; }
.ir-pend { background: #f3e5f5; color: #6a1b9a; }
.ir-act  { display: flex; gap: 11px; margin-bottom: 10px; align-items: flex-start; font-size: 13px; }
.ir-n   { width: 20px; height: 20px; border-radius: 4px; background: #1e3a5f; color: #fff;
          flex-shrink: 0; display: flex; align-items: center; justify-content: center;
          font-size: 10px; font-weight: 700; margin-top: 1px; }
.ir-ab strong { color: #1e3a5f; display: block; margin-bottom: 1px; }
.ir-ab span   { color: #546e7a; font-size: 12px; }
#ir-ftr { background: #f5f7f9; border-top: 1px solid #e0e0e0; padding: 8px 20px;
          display: flex; justify-content: space-between; align-items: center; }
#ir-ftr em { font-size: 11px; color: #90a4ae; font-style: normal; }
.ir-fb { background: none; border: 1px solid #cfd8dc; border-radius: 3px; cursor: pointer;
         font-size: 12px; padding: 1px 6px; color: #546e7a; margin-left: 3px; }
</style>

<!-- ── Outer wrapper (hidden until JS positions it) ── -->
<div id="ir-wrap-outer">

  <!-- AI toggle button -->
  <button id="ir-ai-btn" onclick="irTogglePanel()" type="button">
    <span class="ir-icon-ring">
      <!-- Brain/AI SVG icon -->
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.2"
           stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 2a5 5 0 0 1 5 5v1a5 5 0 0 1-5 5 5 5 0 0 1-5-5V7a5 5 0 0 1 5-5z"/>
        <path d="M12 13v9M8 17h8"/>
        <circle cx="7" cy="7" r="1.5" fill="#fff" stroke="none"/>
        <circle cx="17" cy="7" r="1.5" fill="#fff" stroke="none"/>
      </svg>
    </span>
    Incident Intelligence
    <span class="ir-chevron">&#9660;</span>
  </button>

  <!-- Collapsible panel (hidden by default) -->
  <div id="ir-intel-panel">
    <div id="ir-intel">
      <div id="ir-hdr">
        <div class="t"><span style="font-size:16px;">&#9670;</span> Incident Intelligence Report</div>
        <div class="ts">Auto-generated &nbsp;&#183;&nbsp; $[JS:nowStr]</div>
      </div>

      <div id="ir-body">
        <!-- Snapshot -->
        <div class="ir-c">
          <div class="ir-ct">Incident Snapshot</div>
          <div class="ir-kv"><span class="ir-k">Priority</span>
            <span class="ir-badge" style="background:$[JS:pBg];color:$[JS:pColor];">$[JS:priority]</span></div>
          <div class="ir-kv"><span class="ir-k">State</span>    <span class="ir-v">$[JS:state]</span></div>
          <div class="ir-kv"><span class="ir-k">Category</span> <span class="ir-v">$[JS:catFull]</span></div>
          <div class="ir-kv"><span class="ir-k">Impact</span>   <span class="ir-v">$[JS:impact]</span></div>
          <div class="ir-kv"><span class="ir-k">Urgency</span>  <span class="ir-v">$[JS:urgency]</span></div>
          <div class="ir-kv"><span class="ir-k">Reporter</span> <span class="ir-v">$[JS:caller]</span></div>
          <div class="ir-kv"><span class="ir-k">Assigned</span> <span class="ir-v">$[JS:assigned]</span></div>
          <div class="ir-kv"><span class="ir-k">Group</span>    <span class="ir-v">$[JS:grp]</span></div>
          <div class="ir-kv"><span class="ir-k">Opened</span>   <span class="ir-v">$[JS:opened]</span></div>
        </div>

        <!-- Response Log -->
        <div class="ir-c">
          <div class="ir-ct">Response Log</div>
          <div class="ir-row"><div class="ir-dot ir-done">&#10003;</div><div>Ticket created and logged</div></div>
          <div class="ir-row"><div class="ir-dot ir-done">&#10003;</div><div>Assigned to <strong>$[JS:grp]</strong></div></div>
          <div class="ir-row"><div class="ir-dot ir-done">&#10003;</div><div>Notification sent to assignee</div></div>
          <div class="ir-row"><div class="ir-dot ir-done">&#10003;</div><div>SLA timer active</div></div>
          <div class="ir-row"><div class="ir-dot ir-pend">&#9679;</div><div style="color:#6a1b9a;">Root cause &mdash; pending</div></div>
          <div class="ir-row"><div class="ir-dot ir-pend">&#9679;</div><div style="color:#6a1b9a;">Resolution &mdash; pending</div></div>
        </div>

        <!-- Next Steps -->
        <div class="ir-c">
          <div class="ir-ct">Next Steps</div>
          <div class="ir-act"><div class="ir-n">1</div>
            <div class="ir-ab"><strong>Triage priority</strong>
              <span>Confirm <strong>$[JS:priority]</strong> reflects real business impact; escalate if wider in scope.</span></div></div>
          <div class="ir-act"><div class="ir-n">2</div>
            <div class="ir-ab"><strong>Engage reporter</strong>
              <span>Contact <strong>$[JS:caller]</strong> for reproduction steps or recent changes.</span></div></div>
          <div class="ir-act"><div class="ir-n">3</div>
            <div class="ir-ab"><strong>Search patterns</strong>
              <span>Check open incidents in <strong>$[JS:catFull]</strong> for recurring issues.</span></div></div>
        </div>
      </div>

      <div id="ir-ftr">
        <em>&#9888; AI-assisted &nbsp;&#183;&nbsp; Reflects field data at time of render</em>
        <span>Helpful? <button class="ir-fb">&#128077;</button><button class="ir-fb">&#128078;</button></span>
      </div>
    </div>
  </div>

</div><!-- /ir-wrap-outer -->

<script>
function irTogglePanel() {
  var btn   = document.getElementById('ir-ai-btn');
  var panel = document.getElementById('ir-intel-panel');
  if (!btn || !panel) return;
  var open = panel.classList.contains('visible');
  if (open) {
    panel.classList.remove('visible');
    btn.classList.remove('open');
  } else {
    panel.classList.add('visible');
    btn.classList.add('open');
  }
}

(function placeWidget() {
  var outer = document.getElementById('ir-wrap-outer');
  if (!outer) return;

  function attempt() {
    // Target: just before the Notes / Related Records tab bar
    var tabSelectors = ['.tabs2_list','.tab_header_list','ul[role="tablist"]',
                        '.nav-tabs','.pane_list','#tabs2_section','.tabs2'];
    var anchor = null;
    for (var i = 0; i < tabSelectors.length; i++) {
      anchor = document.querySelector(tabSelectors[i]);
      if (anchor) break;
    }
    if (anchor) {
      var container = anchor;
      for (var j = 0; j < 6; j++) {
        if (!container.parentNode ||
            container.parentNode === document.body) break;
        container = container.parentNode;
      }
      container.parentNode.insertBefore(outer, container);
    } else {
      var fb = document.querySelector('.form-horizontal') ||
               document.getElementById('gsft_main') ||
               document.querySelector('.body_wrap');
      if (fb) fb.appendChild(outer);
    }
    outer.style.display = '';
  }

  setTimeout(attempt, 300);
  setTimeout(attempt, 1200);
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


def patch(table, sid, payload):
    r = requests.patch(f"{SN}/api/now/table/{table}/{sid}",
        auth=AUTH, headers=HJ, data=json.dumps(payload), timeout=30)
    r.raise_for_status()
    return r.json().get("result", {})


def run():
    print("Updating macro with toggle AI button...")
    macs = get("sys_ui_macro", f"name={MACRO_NAME}", "sys_id", 1)
    if macs:
        patch("sys_ui_macro", macs[0]["sys_id"], {"xml": JELLY})
        print(f"  Macro updated: {macs[0]['sys_id']}")
    else:
        print("  Macro not found.")
        return

    print()
    print("=" * 60)
    print("DONE.")
    print()
    print("Steps:")
    print(f"  1. Open {SN}/cache.do  (clears macro cache)")
    print("  2. Open any incident -> Ctrl+Shift+R")
    print("  3. Scroll to bottom of form fields")
    print("  4. See the 'Incident Intelligence' button")
    print("  5. Click it -> panel expands with full report")
    print("  6. Click again -> panel collapses")


if __name__ == "__main__":
    run()
