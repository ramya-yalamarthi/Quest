import requests

from . import config

PAGE_SIZE = 100


def fetch_all_records(table=None, query=None):
    """
    Pages through the ServiceNow Table API and yields raw record dicts.

    table: table name, defaults to config.SERVICENOW_TABLE (e.g. "incident")
    query: optional sysparm_query string (encoded query), e.g. "active=true"
    """
    table = table or config.SERVICENOW_TABLE
    url = f"{config.SERVICENOW_INSTANCE_URL}/api/now/table/{table}"
    auth = (config.SERVICENOW_USERNAME, config.SERVICENOW_PASSWORD)
    headers = {"Accept": "application/json"}

    offset = 0
    while True:
        params = {
            "sysparm_limit": PAGE_SIZE,
            "sysparm_offset": offset,
            "sysparm_display_value": "true",
        }
        if query:
            params["sysparm_query"] = query

        resp = requests.get(url, auth=auth, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        records = resp.json().get("result", [])
        if not records:
            break

        for record in records:
            yield record

        if len(records) < PAGE_SIZE:
            break
        offset += PAGE_SIZE


def fetch_record(table, sys_id):
    table = table or config.SERVICENOW_TABLE
    url = f"{config.SERVICENOW_INSTANCE_URL}/api/now/table/{table}/{sys_id}"
    auth = (config.SERVICENOW_USERNAME, config.SERVICENOW_PASSWORD)
    headers = {"Accept": "application/json"}

    resp = requests.get(url, auth=auth, headers=headers, params={"sysparm_display_value": "true"}, timeout=30)
    resp.raise_for_status()
    return resp.json().get("result")
