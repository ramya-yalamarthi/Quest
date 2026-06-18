from app.mitigation_safety.validation.checks.base import (
    Check,
    CheckContext,
    CheckResult,
    CheckStatus,
)
from app.mitigation_safety.validation.checks.generated_tests import (
    GeneratedTestsCheck,
)
from app.mitigation_safety.validation.checks.regression_suite import (
    RegressionSuiteCheck,
)
from app.mitigation_safety.validation.checks.telemetry_bounds import (
    TelemetryBoundsCheck,
)
from app.mitigation_safety.validation.checks.correlated_incidents import (
    CorrelatedIncidentsCheck,
)
from app.mitigation_safety.validation.checks.human_signoff import (
    HumanSignoffCheck,
)


def default_checks(*, ci, telemetry, incidents, signoff) -> list[Check]:
    """The MS-09 minimum check list, wired with backends.

    Args:
        ci: CIRunner (real or mock)
        telemetry: TelemetrySource
        incidents: CorrelatedIncidentsSource
        signoff: HumanSignoffSource
    """
    return [
        GeneratedTestsCheck(ci=ci),            # (a) code-only
        RegressionSuiteCheck(ci=ci),           # (b)
        TelemetryBoundsCheck(telemetry=telemetry),  # (c)
        CorrelatedIncidentsCheck(source=incidents),  # (d)
        HumanSignoffCheck(source=signoff),     # (e)
    ]


__all__ = [
    "Check",
    "CheckContext",
    "CheckResult",
    "CheckStatus",
    "GeneratedTestsCheck",
    "RegressionSuiteCheck",
    "TelemetryBoundsCheck",
    "CorrelatedIncidentsCheck",
    "HumanSignoffCheck",
    "default_checks",
]
