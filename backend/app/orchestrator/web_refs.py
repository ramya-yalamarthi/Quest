"""
Real reference links for the recommendation (Option B).

Queries Microsoft Learn's PUBLIC search API and returns live result URLs --
no API key, no torch, stdlib only. This replaces the LLM's guessed links with
links that actually resolve. Fully optional: any failure returns [] and the
caller falls back to the model's links.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

_LEARN_SEARCH = "https://learn.microsoft.com/api/search"


def search_refs(query: str, count: int = 3) -> list[dict]:
    """Return up to `count` real reference links [{title, url, source}] from
    Microsoft Learn search. Returns [] on any failure."""
    q = (query or "").strip()
    if not q:
        return []
    params = {"search": q[:200], "$top": str(max(1, count)), "locale": "en-us"}
    url = _LEARN_SEARCH + "?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SupportAI"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception:
        return []

    out = []
    for r in data.get("results", []):
        title, link = r.get("title"), r.get("url")
        if title and link:
            out.append({"title": title, "url": link, "source": "Microsoft Learn"})
        if len(out) >= count:
            break
    return out
