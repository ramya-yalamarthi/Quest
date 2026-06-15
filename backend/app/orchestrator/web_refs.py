"""
Real reference links for the recommendation (Option B).

Queries Microsoft Learn's PUBLIC search API and returns live result URLs --
no API key, no torch, stdlib only. This replaces the LLM's guessed links with
links that actually resolve. Fully optional: any failure returns [] and the
caller falls back to the model's links.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from app.orchestrator.trusted_sources import source_label

_LEARN_SEARCH = "https://learn.microsoft.com/api/search"
_UA = "Mozilla/5.0 (compatible; SupportAI/1.0)"

# Status codes that mean "the page exists, the server is just blocking our bot /
# method" -- we treat these as VALID (the link resolves for a real browser).
_BOT_BLOCKED = {401, 403, 405, 429, 503}


def link_resolves(url: str, timeout: int = 5) -> bool:
    """True if the URL actually resolves (so we never show a dead/hallucinated
    link). 2xx/3xx = good; bot-block codes = good (page exists); 404/410/error =
    dead. Tries a cheap HEAD first, falls back to GET."""
    if not url or not isinstance(url, str):
        return False
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return (resp.getcode() or 200) < 400
        except urllib.error.HTTPError as e:
            if e.code in _BOT_BLOCKED:
                return True               # page exists; just blocking us
            if e.code in (404, 410):
                return False              # genuinely dead
            if method == "GET":
                return False
            # other HTTP error on HEAD -> retry once with GET
        except Exception:
            if method == "GET":
                return False              # DNS/timeout/etc. -> can't confirm, drop
    return False


def validate_links(links: list[dict], count: int = 3, timeout: int = 5) -> list[dict]:
    """Keep only links that actually resolve, de-duped by URL, order preserved,
    capped at `count`. Refreshes the display `source` label from the domain."""
    out, seen = [], set()
    for ln in links or []:
        url = (ln.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        if link_resolves(url, timeout=timeout):
            label = source_label(url) or ln.get("source") or "ref"
            out.append({"title": ln.get("title") or label, "url": url, "source": label})
        if len(out) >= count:
            break
    return out


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
