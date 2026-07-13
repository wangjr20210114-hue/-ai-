import { isEdgeOne } from './auth';

const CONVERSATION_KEY = 'yuanbao.conversationId';
const LEGACY_EDGEONE_KEY = 'eo_conv_id';
const LOCAL_CONVERSATION_ID = 'default-conversation';

function createConversationId(): string {
  return globalThis.crypto?.randomUUID?.()
    ?? `${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
}

export function getOrCreateConversationId(edgeOneRuntime = isEdgeOne): string {
  if (!edgeOneRuntime || typeof window === 'undefined') return LOCAL_CONVERSATION_ID;
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

export function makersConversationHeaders(conversationId: string): Record<string, string> {
  return { 'makers-conversation-id': conversationId };
}
