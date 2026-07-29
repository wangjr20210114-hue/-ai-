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

export type MakerStopResult = {
  status?: 'cancelled' | 'cancel_requested' | 'idle' | 'aborted'
}

export function stopMakerRun(conversationId: string): Promise<MakerStopResult> {
  return apiRequest<MakerStopResult>('/stop', {
    method: 'POST',
    data: { conversation_id: conversationId },
    conversationId: stopControlConversationId(),
    timeout: 15_000,
  })
}

function makerStopConfirmed(result: MakerStopResult): boolean {
  return ['cancelled', 'idle', 'aborted'].includes(String(result.status || ''))
}

async function confirmMakerStop(conversationId: string): Promise<MakerStopResult> {
  const delays = [0, 160, 260, 420, 680, 1000, 1400]
  let last: MakerStopResult = {}
  for (const delay of delays) {
    if (delay) await new Promise((resolve) => setTimeout(resolve, delay))
    // `/stop` is the Makers-owned idempotent cancellation barrier. Repeating
    // it only while Makers reports `cancel_requested` never starts or retries
    // model generation.
    last = await stopMakerRun(conversationId)
    if (makerStopConfirmed(last)) return last
    if (last.status !== 'cancel_requested') return last
  }
  return last
}

export interface ChatStreamCallbacks {
  onPatch: (patch: StreamMessagePatch, event: FlorisStreamEvent) => void
  onDone: () => void
  onError: (message: string) => void
  onLocationRequired?: () => void
}

export interface ActiveChatStream {
  stop: () => Promise<void>
  /** Close only this page's native transport; the Makers run keeps working. */
  detach: () => void
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
  let detached = false
  let locationRequired = false
  let stopState = readManualStopState(conversationId)
  const allowAfterStop = Boolean(stopState)
  if (stopState === 'pending') {
    // Confirm the platform-owned cancellation before opening a new Makers run.
    // Starting /chat first and retrying abortActiveRun from inside that handler
    // can race with the new run and cancel the user's deliberate next message.
    try {
      const result = await confirmMakerStop(conversationId)
      if (!makerStopConfirmed(result)) throw new Error('cancel_pending')
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
      if (detached) return
      callbacks.onDone()
      if (locationRequired && !manuallyStopped) callbacks.onLocationRequired?.()
    },
    onError(message) {
      if (!manuallyStopped && !detached) callbacks.onError(message)
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
        const result = await confirmMakerStop(conversationId)
        if (makerStopConfirmed(result)) {
          writeManualStopState(conversationId, 'confirmed')
        }
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
    detach() {
      if (manuallyStopped || detached) return
      detached = true
      // Closing the native subscriber triggers Makers' documented detached
      // producer path. The same Agent run keeps writing its checkpoint and is
      // recovered through /messages when this conversation opens again.
      requestTask.abort()
    },
  }
}
