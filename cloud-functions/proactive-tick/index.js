import { getStore } from '@edgeone/pages-blob';

function response(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json; charset=utf-8' } });
}

function tickBucket(date = new Date()) {
  return date.toISOString().slice(0, 13).replace(/[-T:]/g, '');
}

async function acquireTick(store, userId) {
  const key = `runtime-locks/proactive/${userId}/${tickBucket()}.json`;
  try {
    await store.setJSON(key, { user_id: userId, acquired_at: Date.now() }, { onlyIfNew: true });
    return true;
  } catch (error) {
    if (String(error?.code || error?.message || '').includes('PRECONDITION_FAILED')) return false;
    throw error;
  }
}

async function tickUser(request, store) {
  const userId = 'local-user';
  if (!await acquireTick(store, userId)) return { user_id: userId, status: 200, ok: true, skipped: true, reason: 'tick_already_claimed' };
  const target = new URL('/proactive', request.url);
  target.search = new URL(request.url).search;
  const headers = new Headers();
  for (const [name, value] of request.headers.entries()) {
    if (!['host', 'content-length', 'connection'].includes(name.toLowerCase())) headers.set(name, value);
  }
  headers.set('Content-Type', 'application/json');
  headers.set('makers-conversation-id', `yuanbao-proactive-${userId}`);
  const result = await fetch(target, {
    method: 'POST', headers, body: JSON.stringify({ operation: 'tick', trigger: 'edgeone_schedule' }),
  });
  const body = await result.json().catch(() => ({ error: `invalid response: ${result.status}` }));
  return { user_id: userId, status: result.status, ok: result.ok, result: body };
}

export async function onRequest(context) {
  const { request } = context;
  if (request.method !== 'POST') return response({ error: 'Method not allowed' }, 405);
  const store = getStore({ name: 'yuanbao-auth', consistency: 'strong' });
  const result = await tickUser(request, store);
  return response(result, result.status);
}
