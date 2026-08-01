import { getStore } from '@edgeone/pages-blob';
import { currentUser, tenantPrefix } from '../../auth/current-user.js';
import { conversationPointerKey, listUserConversations } from '../conversation-index.js';

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

async function listConversationIds(store, user, indexStore) {
  const items = await listUserConversations(store, user, {
    indexStore,
    maxGlobalPages: 50,
  });
  return [...new Set(items.map((item) => String(item?.conversationId || '')).filter(Boolean))];
}

async function clearConversations(store, user, indexStore) {
  let deleted = 0;
  for (let page = 0; page < 100; page += 1) {
    const ids = await listConversationIds(store, user, indexStore);
    if (!ids.length) break;
    for (let offset = 0; offset < ids.length; offset += 8) {
      await Promise.all(ids.slice(offset, offset + 8).map(async (conversationId) => {
        await store.deleteConversation({ conversationId });
        if (indexStore) {
          try {
            await indexStore.delete(conversationPointerKey(user, conversationId));
          } catch (error) {
            if (String(error?.message || '') !== 'Invalid scoped conversation id') throw error;
          }
        }
      }));
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
  const stores = Object.fromEntries(STORE_NAMES.map((name) => [
    name,
    context.__stores?.[name] || getStore({ name, consistency: 'strong' }),
  ]));
  const indexStore = stores['yuanbao-files'];
  if (body.operation === 'inspect') {
    return json({
      ok: true,
      conversation_ids: await listConversationIds(conversationStore, user, indexStore),
    });
  }
  if (body.operation !== 'clear') {
    return json({ error: 'Unsupported operation', code: 'RESET_FAILED' }, 400);
  }

  const conversationsDeleted = await clearConversations(conversationStore, user, indexStore);
  const storeCounts = await Promise.all(
    STORE_NAMES.map((name) => clearStore(stores[name], tenantPrefix(user))),
  );
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
