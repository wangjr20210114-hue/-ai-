import { conversationIndexUserId } from '../auth/current-user.js';

const PAGE_LIMIT = 100;
const GLOBAL_FALLBACK_PAGES = 10;

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
  globalOwnedPages,
  indexedPage,
  uniqueConversations,
};
