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
type ManualStopState = 'pending' | 'confirmed'

function readManualStopState(conversationId: string): ManualStopState | '' {
  const stored = Taro.getStorageSync(manualStopKey(conversationId))
  // Boolean `true` was written by 0.6.0. Treat it as pending so an upgrade
  // safely confirms the old cancellation before opening another run.
  if (stored === true) return 'pending'
  if (
    stored
    && typeof stored === 'object'
    && 'state' in stored
    && (stored.state === 'pending' || stored.state === 'confirmed')
  ) {
    return stored.state
  }
  return ''
}

function writeManualStopState(conversationId: string, state: ManualStopState) {
  Taro.setStorageSync(manualStopKey(conversationId), { state })
}

function stopControlConversationId(): string {
  // Every Makers Agent request requires a syntactically valid conversation
  // header. The stop request must not reuse the target id because the runtime
  // could then make the control request replace the run it is meant to abort.
  return `floris-stop-${Date.now().toString(36)}`
}

function confirmMakerStop(conversationId: string) {
  return apiRequest('/stop', {
    method: 'POST',
    data: { conversation_id: conversationId },
    conversationId: stopControlConversationId(),
    timeout: 15_000,
  })
}

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
  let stopState = readManualStopState(conversationId)
  const allowAfterStop = Boolean(stopState)
  if (stopState === 'pending') {
    // Confirm the platform-owned cancellation before opening a new Makers run.
    // Starting /chat first and retrying abortActiveRun from inside that handler
    // can race with the new run and cancel the user's deliberate next message.
    try {
      await confirmMakerStop(conversationId)
      stopState = 'confirmed'
      writeManualStopState(conversationId, stopState)
    } catch {
      // Keep the marker so Retry performs the same idempotent cancellation
      // barrier. Never resume or recreate the stopped model request.
      throw new Error(translate('stopConfirmFailed'))
    }
  }

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
  if (allowAfterStop) {
    // `startChunkedSse` has now opened the user's deliberate next request.
    // Consume the one-shot permission only here, so a preflight/network
    // failure cannot silently lose it.
    Taro.removeStorageSync(manualStopKey(conversationId))
  }

  return {
    async stop() {
      if (manuallyStopped) return
      manuallyStopped = true
      writeManualStopState(conversationId, 'pending')
      requestTask.abort()
      // Makers owns durable run cancellation. No model request is retried or
      // resumed after an explicit user stop.
      try {
        await confirmMakerStop(conversationId)
        writeManualStopState(conversationId, 'confirmed')
      } catch (reason) {
        // The local request is already aborted. Leave the durable marker
        // pending so the next deliberate send retries cancellation first.
        const detail = reason as { message?: unknown; errMsg?: unknown }
        console.warn(
          '[Floris] Makers stop confirmation is pending',
          String(detail?.message || detail?.errMsg || reason),
        )
      }
    },
  }
}
