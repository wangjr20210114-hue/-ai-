import { getStore } from '@edgeone/pages-blob';
import { listActiveUsers } from '../../auth/identity-repository.js';
import {
  publicIdentity,
  scopedConversationId,
  sessionCookie,
  signSessionToken,
} from '../../auth/session.js';

const SCHEDULE_SESSION_TTL_SECONDS = 10 * 60;

function response(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
}

function tickBucket(date = new Date()) {
  return date.toISOString().slice(0, 13).replace(/[-T:]/g, '');
}

function isConditionalConflict(error) {
  const signal = [error?.code, error?.name, error?.status, error?.statusCode, error?.message]
    .filter((value) => value !== undefined && value !== null)
    .join(' ')
    .toLowerCase();
  return /precondition|already exists|conditional write|conflict|\b409\b|\b412\b/.test(signal);
}

async function acquireTick(store, userId) {
  const key = `runtime-locks/proactive/${userId}/${tickBucket()}.json`;
  try {
    await store.setJSON(
      key,
      { user_id: userId, acquired_at: Date.now() },
      { onlyIfNew: true },
    );
    return key;
  } catch (error) {
    if (isConditionalConflict(error)) return '';
    throw error;
  }
}

export async function tickUser(request, store, identity, env = {}) {
  const userId = identity.id;
  const lockKey = await acquireTick(store, userId);
  if (!lockKey) {
    return { user_id: userId, status: 200, ok: true, skipped: true, reason: 'tick_already_claimed' };
  }

  const target = new URL('/proactive', request.url);
  target.search = new URL(request.url).search;
  const headers = new Headers();
  for (const [name, value] of request.headers.entries()) {
    if (!['host', 'content-length', 'connection'].includes(name.toLowerCase())) headers.set(name, value);
  }
  headers.set('Content-Type', 'application/json');
  headers.set('makers-conversation-id', await scopedConversationId(identity, 'proactive-schedule'));
  const token = await signSessionToken({
    sub: identity.subject_id,
    tenant_id: identity.tenant_id,
    username: identity.username,
    display_name: identity.display_name,
    avatar_url: identity.avatar_url,
    auth_type: identity.auth_type,
    membership: identity.membership,
    roles: identity.roles,
    session_version: identity.session_version,
  }, env, SCHEDULE_SESSION_TTL_SECONDS);
  headers.set('Cookie', sessionCookie(token, {
    maxAge: SCHEDULE_SESSION_TTL_SECONDS,
  }).split(';', 1)[0]);
  try {
    const result = await fetch(target, {
      method: 'POST',
      headers,
      body: JSON.stringify({ operation: 'tick', trigger: 'edgeone_schedule' }),
    });
    const body = await result.json().catch(() => ({ error: `invalid response: ${result.status}` }));
    if (!result.ok) await store.delete(lockKey);
    return { user_id: userId, status: result.status, ok: result.ok, result: body };
  } catch (error) {
    await store.delete(lockKey).catch(() => {});
    throw error;
  }
}

export async function onRequest(context) {
  const { request, env = {} } = context;
  if (request.method !== 'POST') return response({ error: 'Method not allowed' }, 405);
  const store = context.__store || getStore({ name: 'yuanbao-auth', consistency: 'strong' });
  try {
    const users = context.__users || await listActiveUsers(env);
    const identities = users.map((user) => publicIdentity({
      sub: user.user_id,
      tenant_id: user.tenant_id,
      username: user.display_name,
      display_name: user.display_name,
      avatar_url: user.avatar_url,
      auth_type: 'wechat',
      membership: user.membership,
      roles: user.roles,
      session_version: user.session_version,
    }));
    const results = [];
    for (let offset = 0; offset < identities.length; offset += 8) {
      results.push(...await Promise.all(
        identities.slice(offset, offset + 8).map((identity) => (
          tickUser(request, store, identity, env)
        )),
      ));
    }
    return response({
      ok: results.every((item) => item.ok),
      users_scanned: results.length,
      results,
    }, results.some((item) => !item.ok) ? 207 : 200);
  } catch (error) {
    console.error('[proactive-tick] scheduled scan failed', error);
    return response({ error: 'proactive_schedule_failed' }, 500);
  }
}
