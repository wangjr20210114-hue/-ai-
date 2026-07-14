const CONVERSATION_KEY = 'yuanbao.conversationId';
const USER_KEY = 'yuanbao.userId';
const LEGACY_EDGEONE_KEY = 'eo_conv_id';

function createConversationId(): string {
  return globalThis.crypto?.randomUUID?.()
    ?? `${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
}

export function getOrCreateConversationId(): string {
  if (typeof window === 'undefined') return createConversationId();
  try {
    const cached = localStorage.getItem(CONVERSATION_KEY)
      || localStorage.getItem(LEGACY_EDGEONE_KEY);
    if (cached) {
      localStorage.setItem(CONVERSATION_KEY, cached);
      return cached;
    }
    const created = createConversationId();
    localStorage.setItem(CONVERSATION_KEY, created);
    return created;
  } catch {
    return createConversationId();
  }
}

export function getOrCreateUserId(): string {
  if (typeof window === 'undefined') return 'local-user';
  try {
    const cached = localStorage.getItem(USER_KEY);
    if (cached) return cached;
    const created = `user-${createConversationId()}`;
    localStorage.setItem(USER_KEY, created);
    return created;
  } catch {
    return `user-${createConversationId()}`;
  }
}

export function makersConversationHeaders(conversationId: string): Record<string, string> {
  return { 'makers-conversation-id': conversationId };
}
