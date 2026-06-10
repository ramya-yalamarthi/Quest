-- Recommendation Agent (UC3) backend tables. Run ONCE against the live DB.
-- Idempotent: safe to re-run.

-- 1) Engineer like/dislike on recommendation advisories.
CREATE TABLE IF NOT EXISTS recommendation_feedback (
    feedback_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id    uuid NOT NULL,
    ai_event_id  uuid,
    agent_name   text NOT NULL DEFAULT 'recommendation',
    verdict      text NOT NULL,
    comment      text,
    created_by   uuid REFERENCES users(user_id),
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_recommendation_feedback_ticket_id
    ON recommendation_feedback (ticket_id);

-- 2) Allow the supervisor / sub-agent names in the audit table's CHECK.
ALTER TABLE ai_audit_log DROP CONSTRAINT IF EXISTS ai_audit_log_agent_name_check;
ALTER TABLE ai_audit_log ADD CONSTRAINT ai_audit_log_agent_name_check
    CHECK (agent_name IN ('InsightsBuddy','CommCoach',
                          'supervisor','routing','diagnosis','recommendation'));
