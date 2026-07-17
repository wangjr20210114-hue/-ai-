CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  username VARCHAR(64) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  roles TEXT[] NOT NULL DEFAULT ARRAY['user']::TEXT[],
  status VARCHAR(16) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
  connector_token_hash VARCHAR(128),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS users_username_lower_uniq ON users (LOWER(username));
CREATE UNIQUE INDEX IF NOT EXISTS users_connector_token_hash_uniq ON users (connector_token_hash) WHERE connector_token_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS users_status_created_idx ON users (status, created_at);
