import { getStore } from '@edgeone/pages-blob';
import { currentUser, tenantPrefix } from '../../auth/current-user.js';

const STORE_NAMES = ['yuanbao-files'];

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
}

async function clearStore(store, prefix) {
  let deleted = 0;
  for (let page = 0; page < 1000; page += 1) {
    const { blobs = [] } = await store.list({ prefix, consistency: 'strong' });
    if (!blobs.length) break;
    for (let offset = 0; offset < blobs.length; offset += 20) {
      await Promise.all(blobs.slice(offset, offset + 20).map((item) => store.delete(item.key)));
    }
    deleted += blobs.length;
  }
  return deleted;
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
  let user;
  try { user = await currentUser(request, env); } catch { return json({ error: 'Unauthorized' }, 401); }
  const body = await request.json().catch(() => ({}));
  if (String(body.confirmation || '') !== 'DELETE') {
    return json({ error: '请输入 DELETE 确认删除自己的数据', code: 'INVALID_CONFIRMATION' }, 403);
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
    ...STORE_NAMES.map((name) => clearStore(stores[name], tenantPrefix(user))),
  ]);
  return json({
    ok: true,
    conversations_deleted: conversationsDeleted,
    deleted: Object.fromEntries(STORE_NAMES.map((name, index) => [name, storeCounts[index]])),
  });
}

export const __test = {
  clearStore,
  listConversationIds,
  clearConversations,
  STORE_NAMES,
};
