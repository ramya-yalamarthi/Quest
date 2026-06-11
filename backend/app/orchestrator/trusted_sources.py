"""
Trusted-source allowlist for recommendation links (WBS R-05 support).

The Recommendation Agent must NEVER emit URLs from the LLM. Every link it shows
comes from code -- the PREVENTION_LIBRARY entries plus the ServiceNow reference
link -- and each one is filtered through ``is_trusted`` before it leaves the
agent. This keeps the advisory grounded in a fixed set of reputable doc sources
and blocks model-hallucinated links.
"""

from __future__ import annotations

from urllib.parse import urlparse

# hostname -> display source label
TRUSTED_DOMAINS = {
    "learn.microsoft.com": "Microsoft Learn",
    "docs.microsoft.com": "Microsoft Docs",
    "techcommunity.microsoft.com": "Microsoft Tech Community",
    "support.microsoft.com": "Microsoft Support",
    "devblogs.microsoft.com": "Microsoft DevBlogs",
    "docs.servicenow.com": "ServiceNow Docs",
    "support.servicenow.com": "ServiceNow Support KB",
    "stackoverflow.com": "Stack Overflow",
    "serverfault.com": "Server Fault",
    "github.com": "GitHub",
    "reddit.com": "Reddit",
    "cisco.com": "Cisco Support",
    "postgresql.org": "PostgreSQL Docs",
}


def is_trusted(url: str) -> bool:
    """True if the URL's hostname equals, or is a subdomain of, a trusted domain.

    e.g. ``www.cisco.com`` and ``cisco.com`` both pass for ``cisco.com``;
    ``evil-cisco.com`` does not.
    """
    if not url or not isinstance(url, str):
        return False
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    return any(host == d or host.endswith("." + d) for d in TRUSTED_DOMAINS)


def source_label(url: str) -> str:
    """Best-effort display label for a trusted URL (empty string if untrusted)."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return ""
    for d, label in TRUSTED_DOMAINS.items():
        if host == d or host.endswith("." + d):
            return label
    return ""
