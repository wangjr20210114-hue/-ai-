import bcrypt from 'bcryptjs';
import { createUser, findUserByUsername } from '../../_db.js';
import { serializeSession, signToken } from '../../_jwt.js';
import { validPassword, validUsername } from '../../_validate.js';

const json = (data, status = 200, cookie = '') => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json; charset=utf-8', ...(cookie ? { 'Set-Cookie': cookie } : {}) } });

export async function onRequestPost({ request, env }) {
  if (!env.JWT_SECRET || !env.DATABASE_URL) return json({ error: 'server_misconfigured' }, 503);
  const body = await request.json().catch(() => ({}));
  if (!validUsername(body.username)) return json({ error: 'invalid_username' }, 400);
  if (!validPassword(body.password)) return json({ error: 'invalid_password' }, 400);
  if (await findUserByUsername(env, body.username)) return json({ error: 'username_taken' }, 409);
  try {
    const user = await createUser(env, body.username, await bcrypt.hash(body.password, 10));
    const roles = Array.isArray(user.roles) ? user.roles : ['user'];
    const token = await signToken({ sub: user.id, username: user.username, roles }, env);
    return json({ mode: 'multi_user', user: { id: user.id, username: user.username, roles } }, 201, serializeSession(token));
  } catch (error) {
    return json({ error: String(error?.message || '').includes('unique') ? 'username_taken' : 'register_failed' }, String(error?.message || '').includes('unique') ? 409 : 500);
  }
}
