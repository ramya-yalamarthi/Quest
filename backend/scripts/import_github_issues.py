"""
Seed the similarity corpus with REAL solved tickets by importing closed GitHub
issues as RESOLVED D365 Cases.

By default it pulls closed `kind/bug` issues from kubernetes-sigs/karpenter --
real cloud-infra / Kubernetes problems that were fixed -- and creates each one
as a Case in D365, then resolves it (statecode 1). The orchestrator's
similarity corpus is "resolved Cases", so these become the agent's history
automatically -- no agent code change.

Usage:
    cd backend
    # needs the Dataverse env vars (DATAVERSE_URL, AZURE_TENANT_ID,
    # AZURE_CLIENT_ID, AZURE_CLIENT_SECRET) -- same as the live service.
    python3 scripts/import_github_issues.py [LIMIT]

    # optional, raises the GitHub rate limit AND lets it fetch the real
    # resolution (closing comment) per issue:
    GITHUB_TOKEN=ghp_xxx python3 scripts/import_github_issues.py 100

Env / args:
    LIMIT          how many issues to import (arg 1, default 100)
    GH_REPO        owner/repo (default kubernetes-sigs/karpenter)
    GH_LABEL       label filter (default "kind/bug"; set "" for any)
    GITHUB_TOKEN   optional PAT -> higher rate limit + per-issue resolution
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request

# allow `import app...` when run from backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.orchestrator.dataverse import DataverseClient, available  # noqa: E402

GH_REPO = os.getenv("GH_REPO", "kubernetes-sigs/karpenter")
GH_LABEL = os.getenv("GH_LABEL", "kind/bug")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
MAX_DESC = 4000          # cap the description so embeddings stay focused


def _gh(url: str) -> dict:
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    if GITHUB_TOKEN:
        req.add_header("Authorization", f"Bearer {GITHUB_TOKEN}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def fetch_issues(limit: int) -> list:
    """Return solved issues as dicts (number, title, body, url).

    Prefers the bundled JSON snapshot (offline -- no GitHub token, rate limit,
    or SSL needed). Falls back to the live GitHub Search API if the file is
    absent."""
    local = os.getenv("GH_ISSUES_FILE") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "karpenter_issues.json")
    if os.path.exists(local):
        with open(local) as f:
            data = json.load(f)
        print(f"Loaded {len(data)} issues from {os.path.basename(local)} (offline snapshot).")
        return data[:limit]

    q = f"repo:{GH_REPO} type:issue state:closed reason:completed"
    if GH_LABEL:
        q += f' label:"{GH_LABEL}"'
    out, page = [], 1
    while len(out) < limit:
        per = min(100, limit - len(out))
        url = ("https://api.github.com/search/issues?q=" + urllib.parse.quote(q) +
               f"&per_page={per}&page={page}&sort=created&order=desc")
        items = _gh(url).get("items", [])
        if not items:
            break
        for i in items:
            out.append({"number": i["number"], "title": i["title"],
                        "body": i.get("body") or "", "url": i["html_url"]})
        page += 1
        time.sleep(1)        # be gentle with the search API
    return out[:limit]


def fetch_resolution(number: int, url: str) -> str:
    """The last comment usually summarises the fix. Only call this when a token
    is set (otherwise the rate limit would be hit). Falls back to a link."""
    fallback = f"Resolved upstream. See GitHub issue #{number}: {url}"
    if not GITHUB_TOKEN:
        return fallback
    try:
        comments = _gh(f"https://api.github.com/repos/{GH_REPO}/issues/{number}/comments?per_page=100")
        if comments:
            last = comments[-1].get("body") or ""
            if last.strip():
                return (last.strip()[:MAX_DESC] + f"\n\n(Source: GitHub issue #{number} {url})")
    except Exception:
        pass
    return fallback


def main(argv):
    limit = int(argv[1]) if len(argv) > 1 else 100

    if not available():
        print("Dataverse env not set (DATAVERSE_URL / AZURE_*). Aborting.")
        return 1
    client = DataverseClient()

    customer = client.first_customer_bind()
    if not customer:
        print("No account or contact found in D365 to use as the case customer. "
              "Create one account first, then re-run.")
        return 1
    print(f"Using customer {customer}")

    print(f"Fetching up to {limit} closed '{GH_LABEL or 'any'}' issues from {GH_REPO} …")
    issues = fetch_issues(limit)
    print(f"Got {len(issues)} issues. Importing as resolved Cases "
          f"(resolutions: {'real comments' if GITHUB_TOKEN else 'link only — set GITHUB_TOKEN for full text'}) …\n")

    ok = 0
    for n, iss in enumerate(issues, 1):
        title = f"[k8s] {iss['title']}"
        desc = (iss["body"] or iss["title"])[:MAX_DESC]
        try:
            case_id = client.create_incident(title, desc, customer)
            if not case_id:
                print(f"  {n:>3}. SKIP (no id) #{iss['number']} {iss['title'][:60]}")
                continue
            resolution = fetch_resolution(iss["number"], iss["url"])
            client.close_incident(case_id, subject=f"Resolution (GitHub #{iss['number']})",
                                  text=resolution)
            ok += 1
            print(f"  {n:>3}. OK   #{iss['number']} -> {case_id[:8]}…  {iss['title'][:60]}")
        except Exception as exc:
            print(f"  {n:>3}. FAIL #{iss['number']} {iss['title'][:50]} :: {exc}")
        time.sleep(0.3)       # don't hammer Dataverse

    print(f"\nDone. Imported {ok}/{len(issues)} as resolved Cases. "
          "They are now part of the similarity corpus.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
