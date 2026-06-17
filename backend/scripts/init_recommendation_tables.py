"""One-off DB setup for the Recommendation Agent (UC3).

Creates the recommendation_feedback table (if missing) and widens the
ai_audit_log agent_name CHECK so supervisor/routing/diagnosis/recommendation
are allowed. Idempotent -- safe to re-run.

Run from the backend/ directory with the app's DATABASE_URL configured:

    cd backend
    python scripts/init_recommendation_tables.py

(equivalent to applying scripts/recommendation_tables.sql)
"""

from sqlalchemy import text

from app.db.base import Base
from app.db.session import engine
import app.db.models  # noqa: F401  -- register all models
from app.db.models.recommendation_feedback import RecommendationFeedback

_WIDEN_CHECK = """
ALTER TABLE ai_audit_log DROP CONSTRAINT IF EXISTS ai_audit_log_agent_name_check;
ALTER TABLE ai_audit_log ADD CONSTRAINT ai_audit_log_agent_name_check
    CHECK (agent_name IN ('InsightsBuddy','CommCoach',
                          'supervisor','routing','diagnosis','recommendation'));
"""


def main() -> None:
    # 1) create only the new table; create_all skips tables that already exist.
    Base.metadata.create_all(bind=engine, tables=[RecommendationFeedback.__table__])
    print("OK: recommendation_feedback ensured.")

    # 2) widen the audit CHECK constraint.
    with engine.begin() as conn:
        for stmt in filter(None, (s.strip() for s in _WIDEN_CHECK.split(";"))):
            conn.execute(text(stmt))
    print("OK: ai_audit_log agent_name CHECK widened.")


if __name__ == "__main__":
    main()
