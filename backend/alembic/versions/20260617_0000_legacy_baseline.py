"""legacy_baseline: pre-existing app tables required by the mitigation_safety FKs.

Revision ID: 20260617_0000
Revises:
Create Date: 2026-06-17

Creates (idempotently) the schema the legacy app shipped with via raw SQL in
`backend/README.md` and `scripts/recommendation_tables.sql`. This is the
**first** Alembic revision — `down_revision = None`.

Why this exists:
- Production DBs already have these tables; on those, run
    `alembic stamp 20260617_0000`
  ONCE to record this baseline without trying to re-create it. Then
  `alembic upgrade head` will apply the mitigation_safety revision on top.
- Empty/fresh DBs (greenfield deploys, CI) MUST be able to run
    `alembic upgrade head`
  end-to-end without `relation "tickets" does not exist` errors. The
  `CREATE TABLE IF NOT EXISTS` blocks below make that work.

Notes:
- Vector columns are guarded behind `pgvector` extension availability so the
  migration still applies on environments without pgvector (the column is
  simply omitted; the legacy app's embedding features degrade gracefully).
- The `ai_audit_log` CHECK constraint is widened up-front so the orchestrator
  writes succeed without a follow-up ALTER (matches
  `scripts/recommendation_tables.sql`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260617_0000"
down_revision = None
branch_labels = None
depends_on = None


SQL = r"""
CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        BEGIN
            CREATE EXTENSION vector;
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'pgvector extension not available; legacy embedding columns will be skipped';
        END;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS users (
  user_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email          text NOT NULL UNIQUE,
  display_name   text NOT NULL,
  role           text NOT NULL,
  manager_id     uuid REFERENCES users(user_id),
  created_at     timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT users_role_check CHECK (role IN ('REQUESTER','SUPPORT','SUPPORT_MANAGER'))
);

CREATE TABLE IF NOT EXISTS tickets (
  ticket_id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title                  text NOT NULL,
  description            text NOT NULL,
  status                 text NOT NULL DEFAULT 'NEW',
  created_by             uuid REFERENCES users(user_id),
  assigned_to            uuid REFERENCES users(user_id),
  assigned_at            timestamptz,
  escalated_manager_id1  uuid REFERENCES users(user_id),
  escalated_manager_id2  uuid REFERENCES users(user_id),
  escalated_manager1_at  timestamptz,
  escalated_manager2_at  timestamptz,
  created_at             timestamptz NOT NULL DEFAULT now(),
  updated_at             timestamptz NOT NULL DEFAULT now(),
  priority               text DEFAULT 'Normal',
  service_status         text DEFAULT 'OK',
  service                text DEFAULT 'General',
  env                    text DEFAULT 'Production',
  region                 text DEFAULT 'Unknown',
  has_resolution         boolean NOT NULL DEFAULT false,
  ticket_summary         text,
  CONSTRAINT tickets_status_check CHECK (status IN ('NEW','ASSIGNED','RESOLVED'))
);

-- Vector column only if pgvector is installed.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_name = 'tickets' AND column_name = 'embedding'
    ) THEN
      EXECUTE 'ALTER TABLE tickets ADD COLUMN embedding vector(1536)';
    END IF;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS emails (
  email_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ticket_id   uuid REFERENCES tickets(ticket_id) ON DELETE CASCADE,
  type        text NOT NULL,
  subject     text NOT NULL,
  body        text NOT NULL,
  created_by  uuid REFERENCES users(user_id),
  created_at  timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT emails_type_check CHECK (type IN ('DRAFT','APPROVED'))
);

CREATE TABLE IF NOT EXISTS resolutions (
  resolution_id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ticket_id                      uuid NOT NULL REFERENCES tickets(ticket_id),
  resolution_text                text,
  recommendedsteps               jsonb,
  root_cause                     text,
  outcome                        jsonb,
  confidence_score               numeric(5,4),
  reasoning                      text,
  created_by                     uuid REFERENCES users(user_id),
  created_at                     timestamptz NOT NULL DEFAULT now(),
  total_similar_tickets_above70  numeric
);

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_name = 'resolutions' AND column_name = 'embedding'
    ) THEN
      EXECUTE 'ALTER TABLE resolutions ADD COLUMN embedding vector(1536)';
    END IF;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS ai_audit_log (
  ai_event_id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ticket_id                uuid REFERENCES tickets(ticket_id) ON DELETE SET NULL,
  agent_name               text NOT NULL,
  model_name               text NOT NULL DEFAULT 'orchestrator',
  input_json               jsonb NOT NULL DEFAULT '{}'::jsonb,
  output_json              jsonb NOT NULL DEFAULT '{}'::jsonb,
  confidence_json          jsonb,
  supporting_incident_ids  uuid[],
  was_used                 boolean DEFAULT false,
  created_at               timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE ai_audit_log DROP CONSTRAINT IF EXISTS ai_audit_log_agent_name_check;
ALTER TABLE ai_audit_log ADD CONSTRAINT ai_audit_log_agent_name_check
    CHECK (agent_name IN ('InsightsBuddy','CommCoach',
                          'supervisor','routing','diagnosis','recommendation'));

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
"""


def upgrade() -> None:
    op.execute(sa.text(SQL))


def downgrade() -> None:
    # Conservative: do NOT drop legacy tables on downgrade — they may contain
    # production data unrelated to the migration sequence.
    pass
