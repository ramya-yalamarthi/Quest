"""
Prevention recommendation library (WBS task R-05).

A fixed lookup of exactly 12 root-cause types -> a deterministic prevention
recommendation (actions + a monitoring rule + 1-3 hardcoded trusted doc links).

The LLM classifies a ticket into ONE of these 12 keys; the prevention content is
NEVER free-generated -- it is taken from this table so the advice is consistent
and the links are pre-vetted. An unknown / unexpected key falls back to
``config_drift``.
"""

from __future__ import annotations

# The 12 canonical root-cause keys. Keep this list and PREVENTION_LIBRARY in sync;
# the agent enumerates these in its system prompt.
ROOT_CAUSE_KEYS = [
    "os_update_failure",
    "driver_incompatibility",
    "db_connection_exhaustion",
    "db_storage_full",
    "vpn_negotiation_failure",
    "dns_misconfiguration",
    "firewall_rule_change",
    "hardware_thermal",
    "hardware_disk_failure",
    "config_drift",
    "patch_regression",
    "capacity_exhaustion",
]

# Root-cause types whose durable fix always requires a Change Management record
# (deterministic backstop -- forced True even if the LLM says otherwise).
CM_REQUIRED_TYPES = {
    "db_storage_full",
    "firewall_rule_change",
    "patch_regression",
    "capacity_exhaustion",
    "config_drift",
}

_FALLBACK_KEY = "config_drift"


PREVENTION_LIBRARY: dict[str, dict] = {
    "os_update_failure": {
        "prevention_actions": [
            "Stage OS updates in a pilot ring before broad rollout.",
            "Enable a known-good restore point / rollback image prior to patching.",
        ],
        "monitoring_rule": "Alert if post-update boot success rate for a device group drops below 98%.",
        "trusted_links": [
            {"title": "Troubleshoot Windows Update", "url": "https://learn.microsoft.com/windows/deployment/update/windows-update-troubleshooting", "source": "Microsoft Learn"},
        ],
    },
    "driver_incompatibility": {
        "prevention_actions": [
            "Pin approved driver versions in the deployment image.",
            "Validate new drivers against the hardware HCL before release.",
        ],
        "monitoring_rule": "Alert on a spike in device-manager error codes (Code 10/43) across a model.",
        "trusted_links": [
            {"title": "Device and driver installation", "url": "https://learn.microsoft.com/windows-hardware/drivers/install/", "source": "Microsoft Learn"},
        ],
    },
    "db_connection_exhaustion": {
        "prevention_actions": [
            "Right-size the application connection pool and enforce max pool size.",
            "Add connection leak detection and idle-connection timeouts.",
        ],
        "monitoring_rule": "Alert when active DB connections exceed 85% of max for 5 minutes.",
        "trusted_links": [
            {"title": "Troubleshoot connection issues to SQL Server", "url": "https://learn.microsoft.com/sql/database-engine/configure-windows/troubleshoot-connecting-to-the-sql-server-database-engine", "source": "Microsoft Learn"},
            {"title": "PostgreSQL connection settings", "url": "https://www.postgresql.org/docs/current/runtime-config-connection.html", "source": "PostgreSQL Docs"},
        ],
    },
    "db_storage_full": {
        "prevention_actions": [
            "Set autogrowth with capped limits and alert thresholds on data/log files.",
            "Schedule log backups / archiving so the transaction log cannot fill the volume.",
        ],
        "monitoring_rule": "Alert when database volume free space falls below 15%.",
        "trusted_links": [
            {"title": "Manage the size of the transaction log file", "url": "https://learn.microsoft.com/sql/relational-databases/logs/manage-the-size-of-the-transaction-log-file", "source": "Microsoft Learn"},
        ],
    },
    "vpn_negotiation_failure": {
        "prevention_actions": [
            "Standardise IKE/IPsec proposals between client and gateway.",
            "Monitor certificate / MFA token expiry that breaks tunnel negotiation.",
        ],
        "monitoring_rule": "Alert when VPN negotiation-failure events exceed baseline by 3x in 10 minutes.",
        "trusted_links": [
            {"title": "Troubleshoot a VPN client connection", "url": "https://learn.microsoft.com/azure/vpn-gateway/vpn-gateway-troubleshoot-vpn-point-to-site-connection-problems", "source": "Microsoft Learn"},
        ],
    },
    "dns_misconfiguration": {
        "prevention_actions": [
            "Validate DNS zone changes in staging before applying to production resolvers.",
            "Enforce change review on conditional forwarders and record TTLs.",
        ],
        "monitoring_rule": "Alert on a rise in NXDOMAIN / SERVFAIL responses for internal zones.",
        "trusted_links": [
            {"title": "Troubleshoot DNS", "url": "https://learn.microsoft.com/windows-server/networking/dns/troubleshoot/troubleshoot-dns", "source": "Microsoft Learn"},
        ],
    },
    "firewall_rule_change": {
        "prevention_actions": [
            "Require peer review and a rollback plan for every firewall rule change.",
            "Tag rules with an owner and expiry so stale allow/deny rules are revisited.",
        ],
        "monitoring_rule": "Alert when blocked-connection counts for a known-good service spike after a rule change window.",
        "trusted_links": [
            {"title": "Windows Defender Firewall configuration", "url": "https://learn.microsoft.com/windows/security/operating-system-security/network-security/windows-firewall/", "source": "Microsoft Learn"},
        ],
    },
    "hardware_thermal": {
        "prevention_actions": [
            "Schedule preventive cleaning / airflow checks on at-risk units.",
            "Cap sustained CPU load or apply thermal throttling policy on affected models.",
        ],
        "monitoring_rule": "Alert when CPU package temperature stays above threshold for 5 minutes.",
        "trusted_links": [
            {"title": "Fix performance and overheating issues", "url": "https://support.microsoft.com/windows/tips-to-improve-pc-performance-in-windows-b3b3ef5b-5953-fb6a-2e25-b6a3d5fe3a9d", "source": "Microsoft Support"},
        ],
    },
    "hardware_disk_failure": {
        "prevention_actions": [
            "Act on SMART pre-failure warnings; proactively replace flagged disks.",
            "Ensure redundancy (RAID / replication) so a single disk failure is non-fatal.",
        ],
        "monitoring_rule": "Alert on any SMART pre-failure attribute or rising reallocated-sector count.",
        "trusted_links": [
            {"title": "Drive health and storage troubleshooting", "url": "https://learn.microsoft.com/windows-server/storage/storage-spaces/storage-spaces-states", "source": "Microsoft Learn"},
        ],
    },
    "config_drift": {
        "prevention_actions": [
            "Enforce desired-state configuration and remediate drift automatically.",
            "Gate manual production changes behind change control.",
        ],
        "monitoring_rule": "Alert when a host's configuration deviates from its baseline policy.",
        "trusted_links": [
            {"title": "Azure Automation State Configuration", "url": "https://learn.microsoft.com/azure/automation/automation-dsc-overview", "source": "Microsoft Learn"},
        ],
    },
    "patch_regression": {
        "prevention_actions": [
            "Validate patches in a pilot ring and keep a tested rollback package.",
            "Track known-issue advisories before approving broad deployment.",
        ],
        "monitoring_rule": "Alert when error/incident rate for a service rises within 24h of a patch deployment.",
        "trusted_links": [
            {"title": "Windows update history and known issues", "url": "https://support.microsoft.com/windows/windows-update-history", "source": "Microsoft Support"},
        ],
    },
    "capacity_exhaustion": {
        "prevention_actions": [
            "Configure autoscale / burst headroom ahead of demand peaks.",
            "Forecast capacity from usage trends and raise quota before saturation.",
        ],
        "monitoring_rule": "Alert when resource utilisation (CPU/memory/cores) exceeds 80% sustained.",
        "trusted_links": [
            {"title": "Autoscale overview", "url": "https://learn.microsoft.com/azure/azure-monitor/autoscale/autoscale-overview", "source": "Microsoft Learn"},
        ],
    },
}


def normalize_root_cause_type(key: str | None) -> str:
    """Return a valid library key, falling back to config_drift for anything
    unknown / missing."""
    if key and key in PREVENTION_LIBRARY:
        return key
    return _FALLBACK_KEY


def get_prevention(root_cause_type: str | None) -> dict:
    """Look up the deterministic prevention entry for a root-cause type."""
    return PREVENTION_LIBRARY[normalize_root_cause_type(root_cause_type)]


def requires_change_mgmt(root_cause_type: str | None) -> bool:
    """Deterministic CM backstop for the high-impact root-cause types."""
    return normalize_root_cause_type(root_cause_type) in CM_REQUIRED_TYPES
