import { conversationIndexUserId, tenantPrefix } from '../auth/current-user.js';

const PAGE_LIMIT = 100;
const GLOBAL_FALLBACK_PAGES = 10;
const POINTER_PATH = 'conversation-index/v1/';

function conversationPointerPrefix(user) {
  const [canonicalTenant = '', canonicalSubject = ''] = String(user?.id || '').split(':', 2);
  return `${tenantPrefix({
    ...user,
    tenant_id: user?.tenant_id || canonicalTenant,
    subject_id: user?.subject_id || canonicalSubject,
  })}${POINTER_PATH}`;
}

export function conversationItems(result) {
  if (Array.isArray(result)) return result;
  if (Array.isArray(result?.items)) return result.items;
  if (Array.isArray(result?.conversations)) return result.conversations;
  return [];
}

export function conversationCursor(result) {
  return String(result?.nextCursor || result?.next_cursor || '').trim();
}

export function belongsToUser(item, user) {
  const metadata = item?.metadata && typeof item.metadata === 'object' ? item.metadata : {};
  return String(metadata.owner_user_id || '') === user.id
    && String(metadata.tenant_id || '') === user.tenant_id;
}

function uniqueConversations(items, limit = PAGE_LIMIT) {
  const seen = new Set();
  const output = [];
  for (const item of items) {
    const id = String(item?.conversationId || item?.conversation_id || '');
    if (!id || seen.has(id)) continue;
    seen.add(id);
    output.push(item);
    if (output.length >= limit) break;
  }
  return output;
}

function pointerTimestamp(value, fallback = Date.now()) {
  const numeric = Number(value);
  if (Number.isFinite(numeric) && numeric > 0) {
    if (numeric < 100_000_000_000) return Math.round(numeric * 1000);
    if (numeric > 10_000_000_000_000) return Math.round(numeric / 1000);
    return Math.round(numeric);
  }
  const parsed = typeof value === 'string' ? Date.parse(value) : Number.NaN;
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function conversationPointerKey(user, conversationId) {
  const id = String(conversationId || '').trim();
  if (!/^yb7_[0-9a-f]{32}$/i.test(id)) {
    throw new Error('Invalid scoped conversation id');
  }
  return `${conversationPointerPrefix(user)}${id}.json`;
}

export function conversationPointer(user, values = {}) {
  const conversationId = String(values.conversationId || '').trim();
  conversationPointerKey(user, conversationId);
  const metadata = values.metadata && typeof values.metadata === 'object'
    ? values.metadata
    : {};
  const now = Number(values.now || Date.now());
  const createdAt = pointerTimestamp(values.createdAt, now);
  return {
    schemaVersion: 1,
    conversationId,
    createdAt,
    lastMessageAt: pointerTimestamp(values.lastMessageAt, now),
    messageCount: Math.max(0, Number(values.messageCount || 0)),
    metadata: {
      client_conversation_id: String(values.clientConversationId || metadata.client_conversation_id || ''),
      owner_user_id: user.id,
      tenant_id: user.tenant_id,
      title: String(values.title || metadata.title || '历史对话'),
      ...(metadata.yuanbao_chat_run_v1
        ? { yuanbao_chat_run_v1: metadata.yuanbao_chat_run_v1 }
        : {}),
    },
  };
}

export async function writeConversationPointer(indexStore, user, values) {
  const item = conversationPointer(user, values);
  await indexStore.setJSON(
    conversationPointerKey(user, item.conversationId),
    item,
    { cacheControl: 'private, no-store' },
  );
  return item;
}

async function blobOwnedPointers(indexStore, user) {
  const prefix = conversationPointerPrefix(user);
  const { blobs = [] } = await indexStore.list({
    prefix,
    consistency: 'strong',
  });
  const owned = [];
  for (let offset = 0; offset < blobs.length; offset += 20) {
    const values = await Promise.all(blobs.slice(offset, offset + 20).map(async (blob) => {
      try {
        return await indexStore.get(blob.key, {
          type: 'json',
          consistency: 'strong',
        });
      } catch {
        return null;
      }
    }));
    owned.push(...values.filter((item) => belongsToUser(item, user)));
  }
  return uniqueConversations(owned.sort(
    (first, second) => pointerTimestamp(second?.lastMessageAt, 0)
      - pointerTimestamp(first?.lastMessageAt, 0),
  ));
}

async function indexedPage(store, user, userId, order) {
  const result = await store.listConversations({
    userId,
    limit: PAGE_LIMIT,
    order,
  });
  return conversationItems(result).filter((item) => belongsToUser(item, user));
}

async function globalOwnedPages(store, user, maxPages, order = 'desc') {
  const owned = [];
  let after = '';
  for (
    let page = 0;
    page < maxPages && (order === 'asc' || owned.length < PAGE_LIMIT);
    page += 1
  ) {
    const result = await store.listConversations({
      limit: PAGE_LIMIT,
      order,
      ...(after ? { after } : {}),
    });
    owned.push(...conversationItems(result).filter((item) => belongsToUser(item, user)));
    const next = conversationCursor(result);
    if (!next || next === after) break;
    after = next;
  }
  const unique = uniqueConversations(owned, owned.length || PAGE_LIMIT);
  return order === 'asc'
    ? unique.slice(-PAGE_LIMIT).reverse()
    : unique.slice(0, PAGE_LIMIT);
}

export async function listUserConversations(store, user, options = {}) {
  const indexUserId = await conversationIndexUserId(user.id);
  const attempts = [
    [indexUserId, 'desc'],
    [indexUserId, 'asc'],
    // Legacy records used the canonical owner id before the path-safe index
    // contract was introduced. Read them without changing message storage.
    [user.id, 'desc'],
    [user.id, 'asc'],
  ];
  let successfulRead = false;
  let lastError;
  for (const [userId, order] of attempts) {
    try {
      const items = await indexedPage(store, user, userId, order);
      successfulRead = true;
      if (items.length) return uniqueConversations(items);
    } catch (error) {
      lastError = error;
    }
  }

  if (options.indexStore) {
    try {
      const items = await blobOwnedPointers(options.indexStore, user);
      successfulRead = true;
      if (items.length) return items;
    } catch (error) {
      lastError = error;
    }
  }

  try {
    const maxGlobalPages = Math.max(
      1,
      Math.min(50, Number(options.maxGlobalPages) || GLOBAL_FALLBACK_PAGES),
    );
    let items = await globalOwnedPages(
      store,
      user,
      maxGlobalPages,
    );
    if (!items.length) {
      // The current runtime's optimized descending scan can be empty even
      // when the non-optimized ascending global index contains the record.
      items = await globalOwnedPages(store, user, maxGlobalPages, 'asc');
    }
    successfulRead = true;
    return items;
  } catch (error) {
    lastError = error;
  }
  if (!successfulRead && lastError) throw lastError;
  return [];
}

export const __test = {
  blobOwnedPointers,
  globalOwnedPages,
  indexedPage,
  uniqueConversations,
};
