"""Check which tables are accessible and create client script via the correct method."""
import json
import requests
from . import config

SN   = config.SERVICENOW_INSTANCE_URL
AUTH = (config.SERVICENOW_USERNAME, config.SERVICENOW_PASSWORD)
H    = {"Accept": "application/json"}
HJ   = {"Content-Type": "application/json", "Accept": "application/json"}

SCRIPT_NAME = "IcM AI Summary Panel"

CLIENT_SCRIPT = r"""
function onLoad() {
    setTimeout(insertIcM, 400);
}

function insertIcM() {
    if (document.getElementById('sn-icm-panel')) return;

    var priority    = g_form.getDisplayValue('priority')         || 'Not set';
    var category    = g_form.getDisplayValue('category')         || 'Not categorised';
    var sub         = g_form.getDisplayValue('subcategory')      || '';
    var state       = g_form.getDisplayValue('state')            || 'New';
    var caller      = g_form.getDisplayValue('caller_id')        || 'Not specified';
    var assigned    = g_form.getDisplayValue('assigned_to')      || 'Unassigned';
    var grp         = g_form.getDisplayValue('assignment_group') || 'Not assigned';
    var impact      = g_form.getDisplayValue('impact')           || '';
    var urgency     = g_form.getDisplayValue('urgency')          || '';
    var opened      = g_form.getDisplayValue('opened_at')        || '';
    var catFull     = category + (sub ? ' / ' + sub : '');
    var now         = new Date().toLocaleString('en-US',
                        {year:'numeric',month:'short',day:'numeric',
                         hour:'2-digit',minute:'2-digit'});

    var leftItems =
        '<li><strong>Priority:</strong> '    + priority + '</li>' +
        '<li><strong>State:</strong> '       + state    + '</li>' +
        '<li><strong>Category:</strong> '   + catFull  + '</li>' +
        (impact  ? '<li><strong>Impact:</strong> '  + impact  + '</li>' : '') +
        (urgency ? '<li><strong>Urgency:</strong> ' + urgency + '</li>' : '') +
        '<li><strong>Reported by:</strong> ' + caller   + '</li>' +
        '<li><strong>Assigned to:</strong> ' + assigned + ' &mdash; ' + grp + '</li>' +
        (opened  ? '<li><strong>Opened:</strong> '  + opened  + '</li>' : '');

    var doneItems =
        '<li>Incident created and assigned to ' + grp + '</li>' +
        '<li>Automated notification workflow triggered &mdash; assignee alerted</li>' +
        '<li>SLA timer started at ' + (opened || now) + '</li>' +
        '<li>Categorised as <strong>' + catFull + '</strong>, priority <strong>' + priority + '</strong></li>';

    var html =
      '<div id="sn-icm-panel" style="background:#fff;border:1px solid #e0e0e0;border-radius:4px;padding:20px 24px 14px;margin:16px 16px 4px;font-family:Segoe UI,system-ui,Arial,sans-serif;font-size:13.5px;">' +
        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:3px;">' +
          '<span style="font-size:17px;color:#5c6bc0;font-weight:700;">&#10022;</span>' +
          '<span style="font-size:15px;font-weight:600;color:#1a1a1a;">AI summary by IcM Assistant</span>' +
        '</div>' +
        '<div style="font-size:12px;color:#888;margin-bottom:14px;">&#8857; Last updated at ' + now + '</div>' +
        '<div style="border-top:1px solid #e8e8e8;margin-bottom:16px;"></div>' +
        '<div style="display:flex;gap:0;align-items:flex-start;">' +
          '<div style="flex:0 0 62%;padding-right:32px;">' +
            '<p style="margin:0 0 8px;font-weight:700;font-size:14px;color:#1a1a1a;">What we know:</p>' +
            '<ul style="margin:0 0 18px;padding-left:20px;line-height:1.8;">' + leftItems + '</ul>' +
            '<p style="margin:0 0 8px;font-weight:700;font-size:14px;color:#1a1a1a;">What has been done so far:</p>' +
            '<ul style="margin:0;padding-left:20px;line-height:1.8;">' + doneItems + '</ul>' +
          '</div>' +
          '<div style="width:1px;background:#e0e0e0;align-self:stretch;flex-shrink:0;"></div>' +
          '<div style="flex:0 0 38%;padding-left:28px;">' +
            '<p style="margin:0 0 12px;font-size:14px;font-weight:600;border-bottom:1px dashed #aaa;padding-bottom:4px;display:inline-block;">Recommended actions</p>' +
            '<ol style="margin:0;padding-left:16px;line-height:1.8;">' +
              '<li style="margin-bottom:10px;"><strong>Verify priority:</strong> Confirm priority <strong>' + priority + '</strong> matches business impact and escalate if needed.</li>' +
              '<li style="margin-bottom:10px;"><strong>Contact reporter:</strong> Reach out to <strong>' + caller + '</strong> for additional context or to reproduce the issue.</li>' +
              '<li style="margin-bottom:10px;"><strong>Check similar incidents:</strong> Search open incidents in category <strong>' + catFull + '</strong> to identify recurring patterns.</li>' +
            '</ol>' +
          '</div>' +
        '</div>' +
        '<div style="border-top:1px solid #e8e8e8;margin-top:14px;padding-top:10px;display:flex;justify-content:space-between;align-items:center;">' +
          '<div style="font-size:12px;color:#aaa;display:flex;align-items:center;gap:5px;">' +
            '<span>AI-generated content may be incorrect</span>' +
            '<span style="cursor:pointer;" title="Helpful">&#128077;</span>' +
            '<span style="cursor:pointer;" title="Not helpful">&#128078;</span>' +
          '</div>' +
          '<div style="font-size:12px;color:#888;display:flex;align-items:center;gap:5px;">' +
            '<span>Are these actions useful?</span>' +
            '<span style="cursor:pointer;" title="Yes">&#128077;</span>' +
            '<span style="cursor:pointer;" title="No">&#128078;</span>' +
          '</div>' +
        '</div>' +
      '</div>';

    var div = document.createElement('div');
    div.innerHTML = html;
    var panel = div.firstChild;

    var anchors = [
        document.querySelector('.form-horizontal'),
        document.querySelector('form.ng-valid'),
        document.querySelector('[data-model-id]'),
    ];
    for (var i = 0; i < anchors.length; i++) {
        var el = anchors[i];
        if (!el) continue;
        el.insertBefore(panel, el.firstChild);
        return;
    }
    document.body.insertBefore(panel, document.body.firstChild);
}
"""


def try_get(table):
    r = requests.get(f"{SN}/api/now/table/{table}", auth=AUTH, headers=H,
        params={"sysparm_limit": "1"}, timeout=30)
    return r.status_code, r.text[:200]


def run():
    # Check table access
    for t in ["sys_client_script", "sys_script_include", "sys_ui_script"]:
        code, body = try_get(t)
        print(f"  GET {t}: {code}")
        if code != 200:
            print(f"    {body[:150]}")

    # Try POST to sys_client_script with detailed error
    print("\nAttempting to create Client Script...")
    payload = {
        "name":       SCRIPT_NAME,
        "table":      "incident",
        "type":       "onLoad",
        "script":     CLIENT_SCRIPT,
        "active":     "true",
        "global":     "true",
    }
    r = requests.post(f"{SN}/api/now/table/sys_client_script",
        auth=AUTH, headers=HJ, data=json.dumps(payload), timeout=30)
    print(f"  POST sys_client_script: {r.status_code}")
    if r.status_code in (200, 201):
        result = r.json().get("result", {})
        print(f"  Created: {result.get('sys_id')}")
    else:
        print(f"  Error body: {r.text[:400]}")

        # Try via sys_ui_script instead (global JavaScript)
        print("\nFalling back to sys_ui_script...")
        ui_payload = {
            "name":       "icm_ai_summary_script",
            "script":     "/* IcM injected via sys_ui_script - not supported for form injection */",
            "active":     "true",
        }
        r2 = requests.post(f"{SN}/api/now/table/sys_ui_script",
            auth=AUTH, headers=HJ, data=json.dumps(ui_payload), timeout=30)
        print(f"  POST sys_ui_script: {r2.status_code}  {r2.text[:200]}")


if __name__ == "__main__":
    run()
