"""
Keeps a Cloudflare quick-tunnel alive in front of the webhook receiver and
keeps the ServiceNow Business Rule pointed at it.

Quick tunnels (https://*.trycloudflare.com) get a fresh random hostname every
time they start. So whenever the hostname changes, this script rewrites the
`setEndpoint(...)` URL inside the "Sync incident to Postgres" Business Rule
via the ServiceNow Table API — no manual updates needed even across restarts.

Run with:
    python -m servicenow_sync.tunnel_manager
"""
import json
import logging
import re
import subprocess
import time
from pathlib import Path

import requests

from . import config

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("tunnel_manager")

STATE_FILE = Path(__file__).resolve().parent / ".tunnel_url"
URL_RE = re.compile(r"https://[a-zA-Z0-9.-]+\.trycloudflare\.com")
BUSINESS_RULE_NAME = "Sync incident to Postgres"


def _read_last_url():
    if STATE_FILE.exists():
        return STATE_FILE.read_text().strip()
    return None


def _write_last_url(url):
    STATE_FILE.write_text(url)


def _build_script(endpoint_url):
    return f"""(function executeRule(current, previous /*null when async*/) {{
    try {{
        var r = new sn_ws.RESTMessageV2();
        r.setEndpoint('{endpoint_url}');
        r.setHttpMethod('POST');
        r.setRequestHeader('Content-Type', 'application/json');
        r.setRequestHeader('X-Webhook-Secret', '{config.SERVICENOW_WEBHOOK_SECRET}');
        r.setRequestBody(JSON.stringify({{
            sys_id: current.sys_id.toString(),
            table: current.getTableName(),
            number: current.getValue('number')
        }}));
        r.executeAsync();
    }} catch (ex) {{
        gs.error('Postgres sync webhook failed: ' + ex.message);
    }}
}})(current, previous);
"""


def _update_business_rule(base_url):
    auth = (config.SERVICENOW_USERNAME, config.SERVICENOW_PASSWORD)
    api = f"{config.SERVICENOW_INSTANCE_URL}/api/now/table/sys_script"

    resp = requests.get(
        api,
        auth=auth,
        headers={"Accept": "application/json"},
        params={"sysparm_query": f"name={BUSINESS_RULE_NAME}", "sysparm_fields": "sys_id", "sysparm_limit": 1},
        timeout=30,
    )
    resp.raise_for_status()
    results = resp.json().get("result", [])
    if not results:
        logger.error("Business Rule '%s' not found in ServiceNow — create it first (see README).", BUSINESS_RULE_NAME)
        return False

    sys_id = results[0]["sys_id"]
    endpoint_url = f"{base_url}/servicenow/webhook"
    script = _build_script(endpoint_url)

    resp = requests.patch(
        f"{api}/{sys_id}",
        auth=auth,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        data=json.dumps({"script": script}),
        timeout=30,
    )
    resp.raise_for_status()
    logger.info("Updated Business Rule endpoint -> %s", endpoint_url)
    return True


def _sync_url_if_changed(new_url):
    last = _read_last_url()
    if new_url == last:
        return
    logger.info("Tunnel URL changed (%s -> %s); updating ServiceNow Business Rule...", last, new_url)
    if _update_business_rule(new_url):
        _write_last_url(new_url)


def run_forever():
    while True:
        logger.info("Starting cloudflared tunnel for http://localhost:%s ...", config.WEBHOOK_PORT)
        proc = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", f"http://localhost:{config.WEBHOOK_PORT}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        found_url = False
        try:
            for line in proc.stdout:
                logger.info("[cloudflared] %s", line.rstrip())
                match = URL_RE.search(line)
                if match and not found_url:
                    found_url = True
                    _sync_url_if_changed(match.group(0))
        finally:
            proc.wait()

        logger.warning("cloudflared exited (code %s); restarting in 5s...", proc.returncode)
        time.sleep(5)


if __name__ == "__main__":
    run_forever()
