import { neon } from '@neondatabase/serverless';

function databaseUrl(env) {
  const value = String(env?.DATABASE_URL || '').trim();
  if (!value) throw new Error('DATABASE_URL is required for WeChat login');
  return value;
}

/**
 * Bind a verified WeChat subject to exactly one Floris user.
 *
 * The CTE may create a candidate user during a first-login race. The identity
 * unique constraint selects one winner and the final CTE removes any unused
 * candidate in the same statement.
 */
export async function upsertWechatIdentity(env, profile, options = {}) {
  const sql = neon(databaseUrl(env));
  const tenantId = String(env.DEFAULT_TENANT_ID || 'floris').slice(0, 96);
  const subject = String(profile.unionid || profile.openid || '').trim();
  if (!subject) throw new Error('WeChat did not return an openid or unionid');
  const provider = profile.unionid ? 'wechat_unionid' : 'wechat_openid';
  const preferredUserId = String(options.preferredUserId || '').trim();
  const candidateUserId = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(preferredUserId)
    ? preferredUserId
    : crypto.randomUUID();
  const displayName = String(profile.nickname || '微信用户').slice(0, 120);
  const avatarUrl = String(profile.headimgurl || '').slice(0, 1000);
  const profileJson = JSON.stringify({
    openid: String(profile.openid || ''),
    unionid: String(profile.unionid || ''),
    nickname: displayName,
    avatar_url: avatarUrl,
  });
  const [, rows] = await sql.transaction((txn) => [
    txn`SELECT set_config('app.tenant_id', ${tenantId}, true)`,
    txn`
      WITH ensured_tenant AS (
        INSERT INTO tenants (id, slug, name)
        VALUES (${tenantId}, ${tenantId}, ${tenantId})
        ON CONFLICT (id) DO UPDATE SET updated_at = NOW()
        RETURNING id
      ),
      candidate_user AS (
        INSERT INTO users (id, tenant_id, display_name, avatar_url)
        SELECT ${candidateUserId}::uuid, id, ${displayName}, ${avatarUrl}
        FROM ensured_tenant
        RETURNING id, tenant_id
      ),
      bound_identity AS (
        INSERT INTO auth_identities (
          tenant_id, provider, provider_subject, user_id, profile_json
        )
        SELECT tenant_id, ${provider}, ${subject}, id, ${profileJson}::jsonb
        FROM candidate_user
        ON CONFLICT (tenant_id, provider, provider_subject)
        DO UPDATE SET
          profile_json = EXCLUDED.profile_json,
          updated_at = NOW()
        RETURNING user_id, tenant_id
      ),
      refreshed_user AS (
        UPDATE users
        SET display_name = ${displayName}, avatar_url = ${avatarUrl}, updated_at = NOW()
        WHERE id = (SELECT user_id FROM bound_identity)
        RETURNING id
      ),
      removed_orphan AS (
        DELETE FROM users
        WHERE id = ${candidateUserId}::uuid
          AND id <> (SELECT user_id FROM bound_identity)
        RETURNING id
      )
      SELECT
        users.id::text AS user_id,
        users.tenant_id,
        users.display_name,
        users.avatar_url,
        users.membership,
        users.session_version,
        users.roles
      FROM users
      JOIN bound_identity ON bound_identity.user_id = users.id
      LIMIT 1
    `,
  ], { isolationMode: 'Serializable' });
  if (!rows[0]) throw new Error('Unable to bind WeChat identity');
  return rows[0];
}

/** List registered users for one tenant so the native Makers schedule can fan out. */
export async function listActiveUsers(env, limit = 1000) {
  const sql = neon(databaseUrl(env));
  const tenantId = String(env.DEFAULT_TENANT_ID || 'floris').slice(0, 96);
  const safeLimit = Math.max(1, Math.min(5000, Number(limit) || 1000));
  const [, rows] = await sql.transaction((txn) => [
    txn`SELECT set_config('app.tenant_id', ${tenantId}, true)`,
    txn`
      SELECT
        id::text AS user_id,
        tenant_id,
        display_name,
        avatar_url,
        membership,
        session_version,
        roles
      FROM users
      WHERE tenant_id = ${tenantId}
      ORDER BY id
      LIMIT ${safeLimit}
    `,
  ], { readOnly: true });
  return rows;
}
