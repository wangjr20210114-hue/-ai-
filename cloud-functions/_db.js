import { neon } from '@neondatabase/serverless';

let client;
export function getSql(env) {
  const url = env.DATABASE_URL || process.env.DATABASE_URL;
  if (!url) throw new Error('DATABASE_URL is not configured');
  client ||= neon(url);
  return client;
}

export async function findUserByUsername(env, username) {
  const sql = getSql(env);
  const rows = await sql`SELECT id, username, password_hash, roles, status, connector_token_hash, created_at FROM users WHERE LOWER(username)=LOWER(${username}) LIMIT 1`;
  return rows[0] || null;
}

export async function createUser(env, username, passwordHash) {
  const sql = getSql(env);
  const rows = await sql`INSERT INTO users (username, password_hash) VALUES (${username}, ${passwordHash}) RETURNING id, username, roles, status, created_at`;
  return rows[0];
}

export async function listActiveUsers(env, limit = 1000) {
  const sql = getSql(env);
  return sql`SELECT id, username, roles FROM users WHERE status='active' ORDER BY created_at ASC LIMIT ${limit}`;
}

export async function findConnectorUser(env, tokenHash) {
  const sql = getSql(env);
  const rows = await sql`SELECT id, username, roles FROM users WHERE connector_token_hash=${tokenHash} AND status='active' LIMIT 1`;
  return rows[0] || null;
}

export async function updateConnectorHash(env, userId, tokenHash) {
  const sql = getSql(env);
  await sql`UPDATE users SET connector_token_hash=${tokenHash || null}, updated_at=NOW() WHERE id=${userId}::uuid AND status='active'`;
}
