import {
  streamEventPatch,
  type ChatMessage,
  type ChatRequestPayload,
  type ClarificationPrompt,
  type FlorisStreamEvent,
  type StreamMessagePatch,
} from '@floris/contracts'
import Taro from '@tarojs/taro'
import { apiRequest } from './request'
import { startChunkedSse } from './stream'
import { translate } from '@/i18n'

const manualStopKey = (conversationId: string) => `floris.miniapp.manual-stop.${conversationId}`

export interface ChatStreamCallbacks {
  onPatch: (patch: StreamMessagePatch, event: FlorisStreamEvent) => void
  onDone: () => void
  onError: (message: string) => void
  onLocationRequired?: () => void
}

export interface ActiveChatStream {
  stop: () => Promise<void>
}

/** A later clarification is a new interaction even when it reuses one AI bubble. */
export function applyClarificationPatch(
  message: ChatMessage,
  clarification: ClarificationPrompt,
): ChatMessage {
  const changed = message.clarification?.id !== clarification.id
  return {
    ...message,
    clarification,
    ...(changed ? { clarificationAnswered: false } : {}),
  }
}

/**
 * WeChat's native chunked request is the transport. This adapter only maps the
 * existing Floris SSE protocol to shared UI patches; it owns no Agent logic.
 */
export async function startChatStream(
  conversationId: string,
  payload: ChatRequestPayload,
  callbacks: ChatStreamCallbacks,
): Promise<ActiveChatStream> {
  let manuallyStopped = false
  let locationRequired = false
  const allowAfterStop = Boolean(Taro.getStorageSync(manualStopKey(conversationId)))
  if (allowAfterStop) Taro.removeStorageSync(manualStopKey(conversationId))

  const requestTask = await startChunkedSse({
    path: '/chat',
    conversationId,
    data: {
      ...payload,
      ...(allowAfterStop ? { _allow_after_stop: true } : {}),
    },
    onFrame(frame) {
      try {
        const event = JSON.parse(frame) as FlorisStreamEvent
        const patch = streamEventPatch(event)
        if (patch?.error !== undefined && !patch.error.trim()) {
          patch.error = translate('generationFailed')
        }
        if (patch?.requestLocation) locationRequired = true
        if (patch) callbacks.onPatch(patch, event)
      } catch {
        // One malformed heartbeat must not discard later valid SSE frames.
      }
    },
    onDone() {
      callbacks.onDone()
      if (locationRequired && !manuallyStopped) callbacks.onLocationRequired?.()
    },
    onError(message) {
      if (!manuallyStopped) callbacks.onError(message)
    },
  })

  return {
    async stop() {
      if (manuallyStopped) return
      manuallyStopped = true
      Taro.setStorageSync(manualStopKey(conversationId), true)
      requestTask.abort()
      // Makers owns durable run cancellation. No model request is retried or
      // resumed after an explicit user stop.
      await apiRequest('/stop', {
        method: 'POST',
        data: { conversation_id: conversationId },
        timeout: 5_000,
      }).catch(() => undefined)
    },
  }
}
