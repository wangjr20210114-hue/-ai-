CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS tenants (
  id            VARCHAR(96) PRIMARY KEY,
  slug          VARCHAR(96) NOT NULL UNIQUE,
  name          VARCHAR(160) NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       VARCHAR(96) NOT NULL REFERENCES tenants(id),
  display_name    VARCHAR(120) NOT NULL DEFAULT '',
  avatar_url      TEXT NOT NULL DEFAULT '',
  membership      VARCHAR(16) NOT NULL DEFAULT 'free'
                    CHECK (membership IN ('free', 'plus', 'pro')),
  roles           TEXT[] NOT NULL DEFAULT ARRAY['user']::TEXT[],
  session_version INTEGER NOT NULL DEFAULT 1 CHECK (session_version > 0),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (tenant_id, id)
);

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS roles TEXT[] NOT NULL DEFAULT ARRAY['user']::TEXT[];

CREATE TABLE IF NOT EXISTS auth_identities (
  tenant_id        VARCHAR(96) NOT NULL REFERENCES tenants(id),
  provider         VARCHAR(32) NOT NULL,
  provider_subject VARCHAR(255) NOT NULL,
  user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  profile_json     JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (tenant_id, provider, provider_subject)
);

CREATE INDEX IF NOT EXISTS auth_identities_user_idx
  ON auth_identities (tenant_id, user_id);

CREATE TABLE IF NOT EXISTS billing_orders (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          VARCHAR(96) NOT NULL REFERENCES tenants(id),
  user_id            UUID NOT NULL REFERENCES users(id),
  provider           VARCHAR(32) NOT NULL,
  provider_order_id  VARCHAR(160),
  idempotency_key    VARCHAR(160) NOT NULL,
  target_plan        VARCHAR(16) NOT NULL CHECK (target_plan IN ('plus', 'pro')),
  amount_minor       BIGINT NOT NULL CHECK (amount_minor >= 0),
  currency           CHAR(3) NOT NULL,
  status             VARCHAR(24) NOT NULL DEFAULT 'created',
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (tenant_id, provider, idempotency_key),
  UNIQUE (tenant_id, provider, provider_order_id)
);

CREATE TABLE IF NOT EXISTS billing_events (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id          VARCHAR(96) NOT NULL REFERENCES tenants(id),
  provider           VARCHAR(32) NOT NULL,
  provider_event_id  VARCHAR(160) NOT NULL,
  payload_hash       CHAR(64) NOT NULL,
  received_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  processed_at       TIMESTAMPTZ,
  UNIQUE (tenant_id, provider, provider_event_id)
);

-- Production should use a dedicated application role without BYPASSRLS.
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE auth_identities ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE users FORCE ROW LEVEL SECURITY;
ALTER TABLE auth_identities FORCE ROW LEVEL SECURITY;
ALTER TABLE billing_orders FORCE ROW LEVEL SECURITY;
ALTER TABLE billing_events FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS users_tenant_isolation ON users;
CREATE POLICY users_tenant_isolation ON users
  USING (tenant_id = current_setting('app.tenant_id', TRUE))
  WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE));

DROP POLICY IF EXISTS auth_identities_tenant_isolation ON auth_identities;
CREATE POLICY auth_identities_tenant_isolation ON auth_identities
  USING (tenant_id = current_setting('app.tenant_id', TRUE))
  WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE));

DROP POLICY IF EXISTS billing_orders_tenant_isolation ON billing_orders;
CREATE POLICY billing_orders_tenant_isolation ON billing_orders
  USING (tenant_id = current_setting('app.tenant_id', TRUE))
  WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE));

DROP POLICY IF EXISTS billing_events_tenant_isolation ON billing_events;
CREATE POLICY billing_events_tenant_isolation ON billing_events
  USING (tenant_id = current_setting('app.tenant_id', TRUE))
  WITH CHECK (tenant_id = current_setting('app.tenant_id', TRUE));
