-- User identity schema from the TencentEdgeOne makers-agents-auth pattern.
-- Agent state itself remains in Makers LangGraph Store; this table only holds identity.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  username VARCHAR(64) NOT NULL,
  password_hash TEXT NOT NULL,
  roles JSONB NOT NULL DEFAULT '["user"]'::jsonb,
  status VARCHAR(16) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
  connector_token_hash TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS users_username_lower_uq ON users (LOWER(username));
CREATE UNIQUE INDEX IF NOT EXISTS users_connector_token_hash_uq
  ON users (connector_token_hash) WHERE connector_token_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS users_status_created_idx ON users (status, created_at);
