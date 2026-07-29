import type { ChatMessage } from '@floris/contracts'
import { bootstrap, type BootstrapData } from './conversations'

export function conversationRunActive(data: BootstrapData): boolean {
  const status = String(data.run?.status || '')
  if (status === 'running') return true
  if (status !== 'cancel_requested') return false
  const updatedAt = Number(data.run?.updated_at || 0)
  // Makers may briefly expose cancel_requested while the detached writer
  // unwinds. If that checkpoint has not changed for 15 seconds, treating it
  // as an active generation traps the whole client behind a run that already
  // accepted cancellation.
  return !updatedAt || Date.now() / 1000 - updatedAt < 15
}

export interface ConversationRecoveryOptions {
  initial: BootstrapData
  cancelled: () => boolean
  onSnapshot?: (data: BootstrapData) => void
  read?: (conversationId: string) => Promise<BootstrapData>
  wait?: (milliseconds: number) => Promise<void>
  intervalMs?: number
  maxWaitMs?: number
}

export interface ConversationRecoveryResult {
  data: BootstrapData
  timedOut: boolean
}

/**
 * Reconnect to Makers' durable run lifecycle without creating another model
 * request. The original detached Agent continues writing its checkpoint;
 * this helper only polls /messages until that run reaches a terminal state.
 */
export async function recoverConversation(
  conversationId: string,
  options: ConversationRecoveryOptions,
): Promise<ConversationRecoveryResult> {
  const read = options.read || bootstrap
  const wait = options.wait || ((milliseconds: number) => new Promise<void>(
    (resolve) => setTimeout(resolve, milliseconds),
  ))
  const intervalMs = options.intervalMs ?? 1_000
  const maxWaitMs = options.maxWaitMs ?? 120_000
  const startedAt = Date.now()
  let data = options.initial

  while (conversationRunActive(data) && !options.cancelled()) {
    if (Date.now() - startedAt >= maxWaitMs) {
      return { data, timedOut: true }
    }
    await wait(intervalMs)
    if (options.cancelled()) break
    try {
      data = await read(conversationId)
      options.onSnapshot?.(data)
    } catch {
      // A transient mobile network gap must not turn the detached Makers run
      // into a failed or duplicated generation. Keep polling the same run.
    }
  }
  return { data, timedOut: false }
}

export function recoveringMessages(
  remote: ChatMessage[],
  placeholderId: string,
): ChatMessage[] {
  const tail = remote[remote.length - 1]
  if (tail?.role === 'ai') {
    return remote.map((message, index) => (
      index === remote.length - 1 ? { ...message, streaming: true } : message
    ))
  }
  return [
    ...remote,
    {
      id: placeholderId,
      role: 'ai',
      content: '',
      ts: Date.now(),
      streaming: true,
    },
  ]
}
