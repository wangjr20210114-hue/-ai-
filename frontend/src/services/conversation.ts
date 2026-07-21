import type { ChatMessage, ConversationSummary } from '../types';

const CONVERSATION_KEY = 'yuanbao.conversationId';
const CONVERSATION_LIST_KEY = 'yuanbao.conversations';

export function loadLocalConversations(): ConversationSummary[] {
  try {
    const value = JSON.parse(localStorage.getItem(CONVERSATION_LIST_KEY) || '[]') as ConversationSummary[];
    return Array.isArray(value) ? value.filter((item) => item?.id).slice(0, 100) : [];
  } catch { return []; }
}

export function saveLocalConversations(items: ConversationSummary[]): void {
  try { localStorage.setItem(CONVERSATION_LIST_KEY, JSON.stringify(items.slice(0, 100))); }
  catch { /* Remote conversation index remains authoritative. */ }
}

export function createConversationId(): string {
  return globalThis.crypto?.randomUUID?.()
    ?? `${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
}

export function setActiveConversationId(conversationId: string): void {
  if (typeof localStorage === 'undefined') return;
  localStorage.setItem(CONVERSATION_KEY, conversationId);
}

export function getOrCreateConversationId(): string {
  if (typeof window === 'undefined') return createConversationId();
  try {
    const cached = localStorage.getItem(CONVERSATION_KEY);
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

function workspaceActionIds(message: ChatMessage): Set<string> {
  return new Set((message.workspaceActions || []).map((action) => action.id).filter(Boolean));
}

function actionFallbackLike(content: string): boolean {
  return [
    '地点已经核实，请点击下方按钮显示地点',
    '地点已经过真实地点服务核实',
    '腾讯会议确认卡已准备好',
    '日程变更确认卡已准备好',
    '图片任务已准备好',
  ].some((prefix) => content.trim().startsWith(prefix));
}

/** Collapse restored rows that represent the same durable Workspace Action. */
export function coalesceActionMessages(messages: ChatMessage[]): ChatMessage[] {
  const output: ChatMessage[] = [];
  const ownerByAction = new Map<string, number>();
  messages.forEach((message) => {
    const actionIds = [...workspaceActionIds(message)];
    const owner = actionIds.map((id) => ownerByAction.get(id)).find((index) => index !== undefined);
    if (owner === undefined) {
      output.push(message);
      const index = output.length - 1;
      actionIds.forEach((id) => ownerByAction.set(id, index));
      return;
    }
    const existing = output[owner];
    const existingFallback = actionFallbackLike(existing.content);
    const incomingFallback = actionFallbackLike(message.content);
    const richer = existingFallback !== incomingFallback
      ? (existingFallback ? message : existing)
      : (message.content.trim().length > existing.content.trim().length ? message : existing);
    const actions = [...(existing.workspaceActions || []), ...(message.workspaceActions || [])]
      .filter((action, index, all) => all.findIndex((candidate) => candidate.id === action.id) === index);
    actions.forEach((action) => ownerByAction.set(action.id, owner));
    output[owner] = {
      ...existing,
      ...richer,
      id: existing.id,
      ts: existing.ts,
      workspaceActions: actions,
      searchResults: richer.searchResults || existing.searchResults || message.searchResults,
      papers: richer.papers || existing.papers || message.papers,
      followUps: richer.followUps || existing.followUps || message.followUps,
      streaming: false,
    };
  });
  return output;
}

/** Replace a live placeholder and coalesce any checkpoint row carrying the same durable Action. */
export function reconcileCompletedMessage(messages: ChatMessage[], complete: ChatMessage): ChatMessage[] {
  const completedActionIds = workspaceActionIds(complete);
  let duplicateIndex = completedActionIds.size ? messages.findIndex((message) => (
    message.id !== complete.id
    && message.role === 'ai'
    && [...workspaceActionIds(message)].some((actionId) => completedActionIds.has(actionId))
  )) : -1;
  const liveIndex = messages.findIndex((message) => message.id === complete.id);
  if (duplicateIndex < 0 && completedActionIds.size && liveIndex < 0) {
    const lastUserIndex = messages.reduce((last, message, index) => message.role === 'user' ? index : last, -1);
    duplicateIndex = messages.reduce((last, message, index) => (
      index > lastUserIndex && message.role === 'ai' ? index : last
    ), -1);
  }
  if (duplicateIndex < 0) {
    return liveIndex < 0
      ? [...messages, complete]
      : messages.map((message) => message.id === complete.id ? complete : message);
  }
  const duplicate = messages[duplicateIndex];
  const duplicateFallback = actionFallbackLike(duplicate.content);
  const completeFallback = actionFallbackLike(complete.content);
  const richer = duplicateFallback !== completeFallback
    ? (duplicateFallback ? complete : duplicate)
    : (duplicate.content.trim().length >= complete.content.trim().length ? duplicate : complete);
  const actions = [...(duplicate.workspaceActions || []), ...(complete.workspaceActions || [])]
    .filter((action, index, all) => all.findIndex((candidate) => candidate.id === action.id) === index);
  return messages
    .filter((message) => message.id !== complete.id)
    .map((message) => message.id === duplicate.id ? {
      ...duplicate,
      ...richer,
      id: duplicate.id,
      workspaceActions: actions,
      streaming: false,
    } : message);
}

function placeholderConversationTitle(title: string): boolean {
  return !title.trim() || ['新对话', '历史对话'].includes(title.trim());
}

export function reconcileConversationSummary(
  remote: ConversationSummary,
  local?: ConversationSummary,
): ConversationSummary {
  if (!local) return remote;
  return {
    ...remote,
    title: placeholderConversationTitle(remote.title) && !placeholderConversationTitle(local.title)
      ? local.title
      : remote.title,
    messageCount: Math.max(Number(remote.messageCount || 0), Number(local.messageCount || 0)),
    pending: Boolean(remote.pending && local.pending),
    activityStatus: remote.activityStatus || local.activityStatus,
  };
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
  return coalesceActionMessages(output);
}
