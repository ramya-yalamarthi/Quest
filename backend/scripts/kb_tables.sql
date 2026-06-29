-- KB Recommendations (UC: map similar tickets to KB articles, rank by
-- success rate + avg resolution time, per-article thumbs feedback).
-- Run ONCE against the live DB. Idempotent: safe to re-run.

-- 1) Catalog of internal KB articles / troubleshooting guides. Content is
-- ops-maintained (title/url/summary); the stats columns are updated by the
-- app as tickets are resolved using a given article.
CREATE TABLE IF NOT EXISTS kb_articles (
    kb_id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title                 text NOT NULL,
    url                   text,
    summary               text,
    category              text,
    embedding             vector(1536),
    times_recommended     integer NOT NULL DEFAULT 0,
    times_resolved        integer NOT NULL DEFAULT 0,
    total_resolution_hours numeric NOT NULL DEFAULT 0,
    created_at            timestamptz NOT NULL DEFAULT now()
);

-- 2) Which KB articles were surfaced for which ticket, and how well they
-- matched -- the basis for "similar tickets -> KB articles used" mapping.
CREATE TABLE IF NOT EXISTS ticket_kb_mapping (
    mapping_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id      uuid NOT NULL REFERENCES tickets(ticket_id),
    kb_id          uuid NOT NULL REFERENCES kb_articles(kb_id),
    similarity     numeric,
    recommended_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_ticket_kb_mapping_ticket_id ON ticket_kb_mapping (ticket_id);
CREATE INDEX IF NOT EXISTS ix_ticket_kb_mapping_kb_id ON ticket_kb_mapping (kb_id);

-- 3) Per-article engineer thumbs up/down (separate from the overall
-- recommendation_feedback table -- this is feedback on ONE cited KB article).
CREATE TABLE IF NOT EXISTS kb_feedback (
    kb_feedback_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id      uuid NOT NULL REFERENCES tickets(ticket_id),
    kb_id          uuid NOT NULL REFERENCES kb_articles(kb_id),
    verdict        text NOT NULL,  -- 'like' | 'dislike'
    comment        text,
    created_by     uuid REFERENCES users(user_id),
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_kb_feedback_kb_id ON kb_feedback (kb_id);
