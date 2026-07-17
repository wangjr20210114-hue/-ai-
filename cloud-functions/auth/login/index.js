import bcrypt from 'bcryptjs';
import { findUserByUsername } from '../../_db.js';
import { serializeSession, signToken } from '../../_jwt.js';
import { validPassword, validUsername } from '../../_validate.js';

const json = (data, status = 200, cookie = '') => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json; charset=utf-8', ...(cookie ? { 'Set-Cookie': cookie } : {}) } });
const FAKE_HASH = '$2a$10$abcdefghijklmnopqrstuv1234567890123456789012345678901';

export async function onRequestPost({ request, env }) {
  if (!env.JWT_SECRET || !env.DATABASE_URL) return json({ error: 'server_misconfigured' }, 503);
  const body = await request.json().catch(() => ({}));
  if (!validUsername(body.username) || !validPassword(body.password)) return json({ error: 'invalid_credentials' }, 401);
  const user = await findUserByUsername(env, body.username).catch(() => null);
  const valid = await bcrypt.compare(body.password, user?.password_hash || FAKE_HASH);
  if (!user || !valid || user.status !== 'active') return json({ error: 'invalid_credentials' }, 401);
  const roles = Array.isArray(user.roles) ? user.roles : ['user'];
  const token = await signToken({ sub: user.id, username: user.username, roles }, env);
  return json({ mode: 'multi_user', user: { id: user.id, username: user.username, roles } }, 200, serializeSession(token));
}
