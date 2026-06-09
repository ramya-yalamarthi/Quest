"""
Deploys the IcM panel as a sys_ui_script (global JavaScript) that:
  - Detects when an incident form loads
  - Polls for g_form availability
  - Injects the IcM panel at the top of the form

Also finds and adds a simple formatter to the correct form section
(the section that contains the 'number' field).

Run from backend/:
    python -m servicenow_sync.deploy_icm_ui_script
"""
import json
import requests
from . import config

SN   = config.SERVICENOW_INSTANCE_URL
AUTH = (config.SERVICENOW_USERNAME, config.SERVICENOW_PASSWORD)
H    = {"Accept": "application/json"}
HJ   = {"Content-Type": "application/json", "Accept": "application/json"}

# The full client-side injection script
ICM_GLOBAL_SCRIPT = r"""
(function () {
    'use strict';

    var PANEL_ID = 'sn-icm-panel';

    function buildPanel(f) {
        var priority = f('priority')         || 'Not set';
        var category = f('category')         || 'Not categorised';
        var sub      = f('subcategory')      || '';
        var state    = f('state')            || 'New';
        var caller   = f('caller_id')        || 'Not specified';
        var assigned = f('assigned_to')      || 'Unassigned';
        var grp      = f('assignment_group') || 'Not assigned';
        var impact   = f('impact')           || '';
        var urgency  = f('urgency')          || '';
        var opened   = f('opened_at')        || '';
        var catFull  = category + (sub ? ' / ' + sub : '');
        var now      = new Date().toLocaleString('en-US', {
            year:'numeric', month:'short', day:'numeric',
            hour:'2-digit', minute:'2-digit'
        });

        var left =
            '<li><strong>Priority:</strong> '   + priority + '</li>' +
            '<li><strong>State:</strong> '      + state    + '</li>' +
            '<li><strong>Category:</strong> '   + catFull  + '</li>' +
            (impact  ? '<li><strong>Impact:</strong> '  + impact  + '</li>' : '') +
            (urgency ? '<li><strong>Urgency:</strong> ' + urgency + '</li>' : '') +
            '<li><strong>Reported by:</strong> '+ caller   + '</li>' +
            '<li><strong>Assigned to:</strong> '+ assigned +' &mdash; '+ grp +'</li>' +
            (opened  ? '<li><strong>Opened:</strong> '  + opened  + '</li>' : '');

        var done =
            '<li>Incident created and assigned to ' + grp + '</li>' +
            '<li>Automated notification workflow triggered &mdash; assignee alerted</li>' +
            '<li>SLA timer started at ' + (opened || now) + '</li>' +
            '<li>Categorised as <strong>' + catFull + '</strong>, priority <strong>' + priority + '</strong></li>';

        return '<div id="' + PANEL_ID + '" style="background:#fff;border:1px solid #e0e0e0;border-radius:4px;' +
            'padding:20px 24px 14px;margin:16px 0 0;font-family:Segoe UI,system-ui,Arial,sans-serif;font-size:13.5px;">' +
            '<div style="display:flex;align-items:center;gap:8px;margin-bottom:3px;">' +
              '<span style="font-size:17px;color:#5c6bc0;font-weight:700;">&#10022;</span>' +
              '<span style="font-size:15px;font-weight:600;color:#1a1a1a;">AI summary by IcM Assistant</span>' +
            '</div>' +
            '<div style="font-size:12px;color:#888;margin-bottom:14px;">&#8857; Last updated at ' + now + '</div>' +
            '<div style="border-top:1px solid #e8e8e8;margin-bottom:16px;"></div>' +
            '<div style="display:flex;gap:0;align-items:flex-start;">' +
              '<div style="flex:0 0 62%;padding-right:32px;">' +
                '<p style="margin:0 0 8px;font-weight:700;font-size:14px;">What we know:</p>' +
                '<ul style="margin:0 0 18px;padding-left:20px;line-height:1.8;">' + left + '</ul>' +
                '<p style="margin:0 0 8px;font-weight:700;font-size:14px;">What has been done so far:</p>' +
                '<ul style="margin:0;padding-left:20px;line-height:1.8;">' + done + '</ul>' +
              '</div>' +
              '<div style="width:1px;background:#e0e0e0;align-self:stretch;flex-shrink:0;"></div>' +
              '<div style="flex:0 0 38%;padding-left:28px;">' +
                '<p style="margin:0 0 12px;font-size:14px;font-weight:600;' +
                  'border-bottom:1px dashed #aaa;padding-bottom:4px;display:inline-block;">Recommended actions</p>' +
                '<ol style="margin:0;padding-left:16px;line-height:1.8;">' +
                  '<li style="margin-bottom:10px;"><strong>Verify priority:</strong> Confirm priority <strong>' +
                    priority + '</strong> matches business impact; escalate if needed.</li>' +
                  '<li style="margin-bottom:10px;"><strong>Contact reporter:</strong> Reach out to <strong>' +
                    caller + '</strong> for additional context.</li>' +
                  '<li style="margin-bottom:10px;"><strong>Check similar incidents:</strong> Search open incidents ' +
                    'in <strong>' + catFull + '</strong> for recurring patterns.</li>' +
                '</ol>' +
              '</div>' +
            '</div>' +
            '<div style="border-top:1px solid #e8e8e8;margin-top:14px;padding-top:10px;' +
              'display:flex;justify-content:space-between;align-items:center;">' +
              '<div style="font-size:12px;color:#aaa;display:flex;align-items:center;gap:5px;">' +
                '<span>AI-generated content may be incorrect</span>' +
                '<span style="cursor:pointer;">&#128077;</span><span style="cursor:pointer;">&#128078;</span>' +
              '</div>' +
              '<div style="font-size:12px;color:#888;display:flex;align-items:center;gap:5px;">' +
                '<span>Are these actions useful?</span>' +
                '<span style="cursor:pointer;">&#128077;</span><span style="cursor:pointer;">&#128078;</span>' +
              '</div>' +
            '</div>' +
          '</div>';
    }

    function tryInject() {
        if (document.getElementById(PANEL_ID)) return;

        // Only run on incident forms
        var isIncident = (typeof g_form !== 'undefined' && g_form &&
                          typeof g_form.tableName !== 'undefined' &&
                          g_form.tableName === 'incident') ||
                         window.location.href.indexOf('incident.do') > -1;
        if (!isIncident) return;

        // g_form must be ready
        if (typeof g_form === 'undefined' || !g_form ||
            typeof g_form.getDisplayValue !== 'function') return;

        var dv = function(field) { return g_form.getDisplayValue(field) || ''; };
        var html = buildPanel(dv);

        // Build DOM node
        var wrapper = document.createElement('div');
        wrapper.innerHTML = html;
        var panel = wrapper.firstChild;

        // Find the best insertion point
        var anchors = [
            document.querySelector('.form-horizontal'),
            document.querySelector('.form_section'),
            document.querySelector('table.form_group'),
            document.querySelector('#gsft_main form'),
            document.querySelector('form[name="incident"]'),
        ];
        for (var i = 0; i < anchors.length; i++) {
            if (!anchors[i]) continue;
            anchors[i].parentNode.insertBefore(panel, anchors[i]);
            return;
        }
        // Last resort
        var main = document.getElementById('gsft_main') ||
                   document.getElementById('maindiv') ||
                   document.body;
        if (main) main.insertBefore(panel, main.firstChild);
    }

    function poll() {
        tryInject();
        if (!document.getElementById(PANEL_ID)) {
            setTimeout(poll, 600);
        }
    }

    // Start polling after a short delay
    setTimeout(poll, 800);

    // Also hook into ServiceNow's page navigation events
    if (typeof addEvent === 'function') {
        try { addEvent(window, 'gsftPageReady', function() { setTimeout(poll, 500); }); } catch(e) {}
    }
    if (typeof CustomEvent !== 'undefined') {
        document.addEventListener('sp.page.rendered', function() { setTimeout(poll, 500); }, false);
    }
})();
"""


def get(table, query, fields="sys_id,name", limit=10):
    r = requests.get(f"{SN}/api/now/table/{table}", auth=AUTH, headers=H,
        params={"sysparm_query": query, "sysparm_fields": fields,
                "sysparm_display_value": "true", "sysparm_limit": limit},
        timeout=30)
    if r.status_code == 400:
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
    # ── 1. Deploy / update global UI Script ──────────────────────────────────
    print("Deploying IcM UI Script (global JS)...")
    existing = get("sys_ui_script",
        "nameLIKEicm_ai_summary",
        "sys_id,name,active", 5)

    if existing:
        for s in existing:
            patch("sys_ui_script", s["sys_id"], {
                "script":  ICM_GLOBAL_SCRIPT,
                "active":  "true",
                "global":  "true",
            })
            print(f"  Updated: {s['sys_id']} ({s.get('name')})")
    else:
        r = post("sys_ui_script", {
            "name":    "icm_ai_summary_script",
            "script":  ICM_GLOBAL_SCRIPT,
            "active":  "true",
            "global":  "true",
        })
        print(f"  Created UI Script: {r.get('sys_id')}")

    # ── 2. Find the section with the 'number' field (top of default form) ─────
    print("\nFinding incident form section with 'number' field...")
    els = get("sys_ui_element",
        "name=incident^element=number",
        "sys_id,element,sys_ui_section,position", 10)

    number_section_id = None
    for el in els:
        sec = el.get("sys_ui_section") or {}
        sid = sec.get("value") if isinstance(sec, dict) else str(sec or "")
        if sid:
            number_section_id = sid
            print(f"  Found: section {sid} at position {el.get('position')}")
            break

    if number_section_id:
        # ── 3. Add the simple Jelly formatter to that section ─────────────────
        FORMATTER = "icm_ai_summary.xml"
        existing_el = get("sys_ui_element",
            f"sys_ui_section={number_section_id}^element={FORMATTER}",
            "sys_id", 3)
        for old in existing_el:
            requests.delete(f"{SN}/api/now/table/sys_ui_element/{old['sys_id']}",
                auth=AUTH, headers=H, timeout=30)
            print(f"  Removed old element: {old['sys_id']}")

        new_el = post("sys_ui_element", {
            "name":           "incident",
            "sys_ui_section": number_section_id,
            "element":        FORMATTER,
            "type":           "formatter",
            "position":       "-1",
            "size_x":         "2",
            "size_y":         "1",
        })
        print(f"  Added formatter to number section: {new_el.get('sys_id')}")

    print("\n" + "=" * 60)
    print("DONE.")
    print()
    print("TWO mechanisms now deployed:")
    print("  1. Global JS (sys_ui_script) - injects the IcM panel via DOM")
    print("     on any incident form load, works for ALL incidents")
    print("  2. Formatter on the section with the Number field")
    print()
    print("In ServiceNow:")
    print("  1. Open any incident (INC0010658, INC0010672, etc.)")
    print("  2. Ctrl + Shift + R")
    print("  3. The IcM panel should appear at the TOP of the form")


if __name__ == "__main__":
    run()
