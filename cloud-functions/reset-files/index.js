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

async function listConversationIds(store, userId) {
  const ids = [];
  let after;
  for (let page = 0; page < 100; page += 1) {
    const result = await store.listConversations({
      userId,
      limit: 100,
      order: 'desc',
      ...(after ? { after } : {}),
    });
    const items = Array.isArray(result?.items) ? result.items : [];
    ids.push(...items.map((item) => String(item?.conversationId || '')).filter(Boolean));
    after = result?.nextCursor;
    if (!after || items.length < 100) break;
  }
  return [...new Set(ids)];
}

async function clearConversations(store, userId) {
  let deleted = 0;
  for (let page = 0; page < 100; page += 1) {
    const result = await store.listConversations({ userId, limit: 100, order: 'desc' });
    const ids = (Array.isArray(result?.items) ? result.items : [])
      .map((item) => String(item?.conversationId || ''))
      .filter(Boolean);
    if (!ids.length) break;
    for (let offset = 0; offset < ids.length; offset += 8) {
      await Promise.all(ids.slice(offset, offset + 8).map((conversationId) => (
        store.deleteConversation({ conversationId })
      )));
    }
    deleted += ids.length;
  }
  return deleted;
}

export async function onRequest(context) {
  const { request, env = {} } = context;
  if (request.method !== 'POST') return json({ error: 'Method not allowed' }, 405);
  const user = await currentUser(request, env);
  const body = await request.json().catch(() => ({}));
  const configured = String(env.DATA_CLEAR_PASSWORD || '');
  if (!configured) return json({ error: '数据清理功能暂不可用', code: 'RESET_NOT_CONFIGURED' }, 503);
  if (!secureEqual(body.password, configured)) {
    return json({ error: '密码不正确', code: 'INVALID_PASSWORD' }, 403);
  }

  const conversationStore = context.__conversationStore || context.agent?.store;
  if (!conversationStore) {
    return json({ error: '数据清理功能暂不可用', code: 'RESET_NOT_CONFIGURED' }, 503);
  }
  if (body.operation === 'inspect') {
    return json({
      ok: true,
      conversation_ids: await listConversationIds(conversationStore, user.id),
    });
  }
  if (body.operation !== 'clear') {
    return json({ error: 'Unsupported operation', code: 'RESET_FAILED' }, 400);
  }

  const stores = Object.fromEntries(STORE_NAMES.map((name) => [
    name,
    context.__stores?.[name] || getStore({ name, consistency: 'strong' }),
  ]));
  const [conversationsDeleted, ...storeCounts] = await Promise.all([
    clearConversations(conversationStore, user.id),
    ...STORE_NAMES.map((name) => clearStore(stores[name])),
  ]);
  return json({
    ok: true,
    conversations_deleted: conversationsDeleted,
    deleted: Object.fromEntries(STORE_NAMES.map((name, index) => [name, storeCounts[index]])),
  });
}

export const __test = {
  secureEqual,
  clearStore,
  listConversationIds,
  clearConversations,
  STORE_NAMES,
};
