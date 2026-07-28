import type { ChatMessage, SearchMeta } from './types'

/** A structured result is durable even when the Agent intentionally emits no prose. */
export function hasDurableAssistantPayload(message?: ChatMessage): boolean {
  if (!message) return false
  return message.role === 'ai' && (
    Boolean(message.content.trim())
    || Boolean(message.clarification)
    || Boolean(message.workspaceActions?.length)
    || Boolean(message.papers?.length)
    || Boolean(message.proactive)
  )
}

export function isDurableChatMessage(message: ChatMessage): boolean {
  return !message.failed && (
    message.role === 'user' || hasDurableAssistantPayload(message)
  )
}

export function settleStoppedMessages(messages: ChatMessage[]): ChatMessage[] {
  return messages
    .filter((message) => (
      !message.streaming
      || message.role === 'user'
      || hasDurableAssistantPayload(message)
    ))
    .map((message) => message.streaming ? { ...message, streaming: false } : message)
}

function messageFingerprint(message: ChatMessage): string {
  if (message.role === 'ai' && message.clarification?.id) {
    return `${message.role}\u0000clarification:${message.clarification.id}`
  }
  if (message.role === 'ai' && message.workspaceActions?.length) {
    return `${message.role}\u0000actions:${message.workspaceActions.map((action) => action.id).sort().join(',')}`
  }
  if (message.role === 'ai' && message.papers?.length) {
    return `${message.role}\u0000papers:${message.papers.map((paper) => paper.arxiv_id || paper.arxiv_url || paper.title).join(',')}`
  }
  if (message.role === 'ai' && message.proactive) {
    return `${message.role}\u0000proactive:${message.id}`
  }
  return `${message.role}\u0000${message.content.trim()}`
}

function mergeSearchResults(
  preferred?: SearchMeta,
  fallback?: SearchMeta,
): SearchMeta | undefined {
  if (!preferred) return fallback
  if (!fallback) return preferred
  return {
    ...fallback,
    ...preferred,
    results: preferred.results?.length ? preferred.results : fallback.results,
    media: preferred.media?.length ? preferred.media : fallback.media,
    media_pending: preferred.media?.length || fallback.media?.length
      ? false
      : (preferred.media_pending ?? fallback.media_pending),
  }
}

/**
 * Reconcile Makers checkpoints with the small native-device cache.
 *
 * Makers remains authoritative. The cache only preserves a completed local
 * tail or an explicitly retained live stream while the checkpoint catches up.
 */
export function mergeMessages(
  remote: ChatMessage[],
  local: ChatMessage[],
  options: { preserveStreaming?: boolean } = {},
): ChatMessage[] {
  const preserveStreaming = Boolean(options.preserveStreaming)
  const durableRemote = remote.filter(isDurableChatMessage)
  const durableLocal = local.filter((message) => (
    isDurableChatMessage(message)
    || (!message.failed && preserveStreaming && Boolean(message.streaming))
  ))
  const localByFingerprint = new Map<string, number[]>()
  durableLocal.forEach((message, index) => {
    const key = messageFingerprint(message)
    localByFingerprint.set(key, [...(localByFingerprint.get(key) || []), index])
  })
  const consumed = new Set<number>()
  const output = durableRemote.map((remoteMessage) => {
    const matches = localByFingerprint.get(messageFingerprint(remoteMessage)) || []
    const localIndex = matches.find((index) => !consumed.has(index))
    if (localIndex === undefined) return { ...remoteMessage, streaming: false }
    consumed.add(localIndex)
    const localMessage = durableLocal[localIndex]
    return {
      ...localMessage,
      ...remoteMessage,
      id: remoteMessage.id,
      ts: localMessage.ts > 1_000_000_000_000 ? localMessage.ts : remoteMessage.ts,
      searchResults: mergeSearchResults(remoteMessage.searchResults, localMessage.searchResults),
      workspaceActions: remoteMessage.workspaceActions || localMessage.workspaceActions,
      papers: remoteMessage.papers || localMessage.papers,
      followUps: remoteMessage.followUps || localMessage.followUps,
      streaming: false,
    }
  })
  const lastRemoteMatch = consumed.size ? Math.max(...consumed) : -1
  const unmatchedSuffix = durableLocal.slice(lastRemoteMatch + 1)
  const lastCompletedLocalOffset = unmatchedSuffix.reduce(
    (last, message, index) => hasDurableAssistantPayload(message) ? index : last,
    -1,
  )
  durableLocal.forEach((message, index) => {
    const isLiveTail = preserveStreaming && Boolean(message.streaming) && index > lastRemoteMatch
    if (
      !consumed.has(index)
      && index > lastRemoteMatch
      && (index <= lastRemoteMatch + 1 + lastCompletedLocalOffset || isLiveTail)
    ) {
      output.push({ ...message, streaming: isLiveTail })
    }
  })
  return output
}

export function restoredConversationWasInterrupted(
  messages: ChatMessage[],
  runActive: boolean,
  liveTransport = false,
): boolean {
  if (liveTransport) return false
  const tail = messages[messages.length - 1]
  if (tail && hasDurableAssistantPayload(tail)) return false
  return runActive || tail?.role === 'user'
}
