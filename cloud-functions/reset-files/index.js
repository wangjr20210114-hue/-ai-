import { getStore } from '@edgeone/pages-blob';
import { currentUser } from '../../auth/current-user.js';

const STORE_NAMES = ['yuanbao-files', 'yuanbao-acceptance-shared', 'yuanbao-auth'];

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
}

function secureEqual(left, right) {
  const first = new TextEncoder().encode(String(left || ''));
  const second = new TextEncoder().encode(String(right || ''));
  let difference = first.length ^ second.length;
  const length = Math.max(first.length, second.length);
  for (let index = 0; index < length; index += 1) {
    difference |= (first[index] || 0) ^ (second[index] || 0);
  }
  return difference === 0;
}

async function clearStore(store) {
  const { blobs } = await store.list({ consistency: 'strong' });
  for (let offset = 0; offset < blobs.length; offset += 20) {
    await Promise.all(blobs.slice(offset, offset + 20).map((item) => store.delete(item.key)));
  }
  return blobs.length;
}

export async function onRequest(context) {
  const { request, env = {} } = context;
  if (request.method !== 'POST') return json({ error: 'Method not allowed' }, 405);
  await currentUser(request, env);
  const body = await request.json().catch(() => ({}));
  const configured = String(env.DATA_CLEAR_PASSWORD || '');
  if (!configured) return json({ error: '数据清理功能暂不可用', code: 'RESET_NOT_CONFIGURED' }, 503);
  if (!secureEqual(body.password, configured)) {
    return json({ error: '密码不正确', code: 'INVALID_PASSWORD' }, 403);
  }

  const deleted = {};
  for (const name of STORE_NAMES) {
    const store = context.__stores?.[name] || getStore({ name, consistency: 'strong' });
    deleted[name] = await clearStore(store);
  }
  return json({ ok: true, deleted });
}

export const __test = { secureEqual, clearStore, STORE_NAMES };
