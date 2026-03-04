# Backend

## Setup

### Environment Variables

Create a `.env` file in the `backend/` directory with the following variables:

```env
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/dbname

# JWT Authentication
JWT_SECRET=your-secret-key
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=480

# Azure OpenAI (for LLM)
OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com
OPENAI_API_KEY=your-api-key
LLM_MODEL=gpt-4.1
LLM_API_VERSION=2024-12-01-preview

# Bing Search API (Optional - for web search)
# Get your key from https://portal.azure.com
BING_SEARCH_API_KEY=your-bing-search-api-key
BING_SEARCH_ENDPOINT=https://api.bing.microsoft.com/v7.0/search
```

**Note:** If `BING_SEARCH_API_KEY` is not provided, the system will use DuckDuckGo as a fallback for web search.

### Web Search Feature

The system now includes an intelligent web search agent that:
- Searches across public websites for similar discussions and resolutions
- Uses LLM to build optimized search queries
- Filters and ranks results by relevance
- Extracts actionable solution steps from web pages
- Supports multiple sources (official docs, forums, communities)

The web search appears under "Web Solutions" in the ticket analysis view.

## Database schema (PostgreSQL)

Run these queries in order to create the schema exactly as shown in the DB output.

```sql
-- Extensions
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

-- Users
CREATE TABLE IF NOT EXISTS users (
  user_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text NOT NULL UNIQUE,
  display_name text NOT NULL,
  role text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT users_role_check CHECK (role IN ('REQUESTER', 'SUPPORT', 'SUPPORT_MANAGER'))
);

-- Tickets
CREATE TABLE IF NOT EXISTS tickets (
  ticket_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title text NOT NULL,
  description text NOT NULL,
  status text NOT NULL DEFAULT 'NEW',
  created_by uuid NULL,
  assigned_to uuid NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  embedding vector(1536) NULL,
  assigned_at timestamptz NULL,
  escalated_manager_id1 uuid NULL,
  escalated_manager_id2 uuid NULL,
  escalated_manager1_at timestamptz NULL,
  escalated_manager2_at timestamptz NULL,
  CONSTRAINT tickets_status_check CHECK (status IN ('NEW', 'ASSIGNED', 'RESOLVED')),
  CONSTRAINT tickets_created_by_fkey FOREIGN KEY (created_by) REFERENCES users(user_id),
  CONSTRAINT tickets_assigned_to_fkey FOREIGN KEY (assigned_to) REFERENCES users(user_id),
  CONSTRAINT tickets_escalated_manager_id1_fkey FOREIGN KEY (escalated_manager_id1) REFERENCES users(user_id),
  CONSTRAINT tickets_escalated_manager_id2_fkey FOREIGN KEY (escalated_manager_id2) REFERENCES users(user_id)
);

-- Emails
CREATE TABLE IF NOT EXISTS emails (
  email_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ticket_id uuid NULL,
  type text NOT NULL,
  subject text NOT NULL,
  body text NOT NULL,
  created_by uuid NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT emails_type_check CHECK (type IN ('DRAFT', 'APPROVED')),
  CONSTRAINT emails_created_by_fkey FOREIGN KEY (created_by) REFERENCES users(user_id),
  CONSTRAINT emails_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES tickets(ticket_id) ON DELETE CASCADE
);

-- Resolutions
CREATE TABLE IF NOT EXISTS resolutions (
  resolution_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ticket_id uuid NOT NULL,
  resolution_text text NOT NULL,
  root_cause text NULL,
  outcome text NULL,
  confidence_score numeric(5,4) NULL,
  reasoning text NULL,
  is_final boolean DEFAULT false,
  is_kb boolean DEFAULT false,
  embedding vector(1536) NULL,
  created_by uuid NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT resolutions_outcome_check CHECK (outcome IN ('success', 'fail', 'partial', 'pending')),
  CONSTRAINT resolutions_created_by_fkey FOREIGN KEY (created_by) REFERENCES users(user_id),
  CONSTRAINT resolutions_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES tickets(ticket_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS resolutions_embedding_idx
  ON resolutions USING hnsw (embedding vector_cosine_ops)
  WHERE embedding IS NOT NULL AND is_kb = true;

-- AI audit log
CREATE TABLE IF NOT EXISTS ai_audit_log (
  ai_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ticket_id uuid NULL,
  agent_name text NOT NULL,
  model_name text NOT NULL,
  input_json jsonb NOT NULL,
  output_json jsonb NOT NULL,
  confidence_json jsonb NULL,
  supporting_incident_ids uuid[] NULL,
  was_used boolean DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ai_audit_log_agent_name_check CHECK (agent_name IN ('InsightsBuddy', 'CommCoach')),
  CONSTRAINT ai_audit_log_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES tickets(ticket_id) ON DELETE SET NULL
);
```
