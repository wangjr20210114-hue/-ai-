import type { ChatMessage, ConversationSummary } from '../types';

const CONVERSATION_KEY = 'yuanbao.conversationId';
const CONVERSATION_LIST_KEY = 'yuanbao.conversations';

function scopedKey(key: string): string {
  if (typeof sessionStorage === 'undefined') return key;
  try {
    const scope = sessionStorage.getItem('yuanbao.userScope') || 'local-user';
    return scope === 'local-user' ? key : `${key}.${scope}`;
  } catch { return key; }
}

export function loadLocalConversations(): ConversationSummary[] {
  try {
    const value = JSON.parse(localStorage.getItem(scopedKey(CONVERSATION_LIST_KEY)) || '[]') as ConversationSummary[];
    return Array.isArray(value) ? value.filter((item) => item?.id).slice(0, 100) : [];
  } catch { return []; }
}

export function saveLocalConversations(items: ConversationSummary[]): void {
  try { localStorage.setItem(scopedKey(CONVERSATION_LIST_KEY), JSON.stringify(items.slice(0, 100))); }
  catch { /* Remote conversation index remains authoritative. */ }
}

export function createConversationId(): string {
  return globalThis.crypto?.randomUUID?.()
    ?? `${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
}

export function setActiveConversationId(conversationId: string): void {
  if (typeof localStorage === 'undefined') return;
  localStorage.setItem(scopedKey(CONVERSATION_KEY), conversationId);
}

export function getOrCreateConversationId(): string {
  if (typeof window === 'undefined') return createConversationId();
  try {
    const cached = localStorage.getItem(scopedKey(CONVERSATION_KEY));
    if (cached) {
      localStorage.setItem(scopedKey(CONVERSATION_KEY), cached);
      return cached;
    }
    const created = createConversationId();
    localStorage.setItem(scopedKey(CONVERSATION_KEY), created);
    return created;
  } catch {
    return createConversationId();
  }
}

export function makersConversationHeaders(conversationId: string): Record<string, string> {
  return { 'makers-conversation-id': conversationId };
}

export function durableMessageCount(messages: ChatMessage[]): number {
  return messages.filter((message) => (
    !message.failed && (message.role === 'user' || (message.role === 'ai' && Boolean(message.content.trim())))
  )).length;
}

export function canReusePendingConversation(
  candidate: ConversationSummary,
  currentConversationId: string,
  currentMessages: ChatMessage[],
): boolean {
  return Boolean(candidate.pending)
    && !candidate.messageCount
    && (candidate.id !== currentConversationId || durableMessageCount(currentMessages) === 0);
}

export function settleStoppedMessages(messages: ChatMessage[]): ChatMessage[] {
  return messages
    .filter((message) => !message.streaming || message.role === 'user' || Boolean(message.content.trim()))
    .map((message) => message.streaming ? { ...message, streaming: false } : message);
}

function messageFingerprint(message: ChatMessage): string {
  return `${message.role}\u0000${message.content.trim()}`;
}

/** Reconcile sequence occurrences; checkpoint indexes and browser timestamps are incomparable. */
export function mergeMessages(remote: ChatMessage[], local: ChatMessage[]): ChatMessage[] {
  remote = remote.filter((message) => !message.failed && (message.role === 'user' || message.content.trim()));
  local = local.filter((message) => !message.failed && (message.role === 'user' || message.content.trim()));
  const localByFingerprint = new Map<string, number[]>();
  local.forEach((message, index) => {
    const key = messageFingerprint(message);
    localByFingerprint.set(key, [...(localByFingerprint.get(key) || []), index]);
  });
  const consumed = new Set<number>();
  const output = remote.map((remoteMessage) => {
    const matches = localByFingerprint.get(messageFingerprint(remoteMessage)) || [];
    const localIndex = matches.find((index) => !consumed.has(index));
    if (localIndex === undefined) return { ...remoteMessage, streaming: false };
    consumed.add(localIndex);
    const localMessage = local[localIndex];
    return {
      ...localMessage,
      ...remoteMessage,
      id: remoteMessage.id,
      ts: localMessage.ts > 1_000_000_000_000 ? localMessage.ts : remoteMessage.ts,
      searchResults: remoteMessage.searchResults || localMessage.searchResults,
      workspaceActions: remoteMessage.workspaceActions || localMessage.workspaceActions,
      papers: remoteMessage.papers || localMessage.papers,
      streaming: false,
    };
  });
  const lastRemoteMatch = consumed.size ? Math.max(...consumed) : -1;
  const unmatchedSuffix = local.slice(lastRemoteMatch + 1);
  const lastCompletedLocalOffset = unmatchedSuffix.reduce(
    (last, message, index) => message.role === 'ai' && message.content.trim() ? index : last,
    -1,
  );
  local.forEach((message, index) => {
    // Makers is authoritative for the restored prefix. Local rows before its
    // latest match are stale optimistic/error-era artifacts. A trailing
    // user-only suffix is also an interrupted/failed optimistic send; append
    // only locally completed turns that Makers has not synchronized yet.
    if (!consumed.has(index)
      && index > lastRemoteMatch
      && index <= lastRemoteMatch + 1 + lastCompletedLocalOffset) {
      output.push({ ...message, streaming: false });
    }
  });
  return output;
}
