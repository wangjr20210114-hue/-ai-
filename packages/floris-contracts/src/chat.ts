import type {
  ChatMessage,
  ClarificationPrompt,
  FlorisStreamEvent,
  PaperInfo,
  SearchMeta,
  WorkspaceAction,
} from './types'

export interface ChatRequestPayload {
  activity: string
  text: string
  message_id: string
  client_message_id: string
  client_message?: ChatMessage
  clarification_response?: {
    id: string
    source_message_id: string
    answers: Array<{ id: string; label: string; value: string | string[] }>
  }
  reference_images: string[]
  response_language: string
  current_location?: Record<string, unknown>
  location_request?: Record<string, unknown>
  _location_retry?: boolean
  _allow_after_stop?: boolean
}

export function createConversationId(prefix: string, now = Date.now(), random = Math.random): string {
  const suffix = `${now.toString(36)}${random().toString(36).slice(2, 14)}`
    .replace(/[^0-9A-Za-z]/g, '')
    .slice(0, Math.max(8, 36 - prefix.length))
  return `${prefix}${suffix}`
}

export function createChatPayload(
  message: ChatMessage,
  responseLanguage: string,
): ChatRequestPayload {
  return {
    activity: 'asked',
    text: message.content,
    message_id: message.id,
    client_message_id: message.id,
    client_message: message,
    reference_images: [],
    response_language: responseLanguage,
  }
}

export function createClarificationPayload(
  clarification: ClarificationPrompt,
  values: Record<string, string | string[]>,
  sourceMessageId: string,
  responseLanguage: string,
): ChatRequestPayload {
  const id = `clarification-${Date.now()}`
  const answers: Array<{ id: string; label: string; value: string | string[] }> = []
  clarification.fields.forEach((field) => {
    const value = values[field.id]
    const protocolValue = (item: string) => field.option_values?.[item] || item
    if (Array.isArray(value)) {
      if (value.length) answers.push({ id: field.id, label: field.label, value: value.map(protocolValue) })
      return
    }
    const text = String(value || '').trim()
    if (text) answers.push({ id: field.id, label: field.label, value: protocolValue(text) })
  })
  return {
    activity: 'clarification_answered',
    text: answers.map((answer) => `${answer.label}：${Array.isArray(answer.value) ? answer.value.join('、') : answer.value}`).join('\n'),
    message_id: id,
    client_message_id: id,
    clarification_response: {
      id: clarification.id,
      source_message_id: sourceMessageId,
      answers,
    },
    reference_images: [],
    response_language: responseLanguage,
  }
}

/** Resume the same Agent turn after native location permission resolves. */
export function createLocationRetryPayload(
  payload: ChatRequestPayload,
  location?: Record<string, unknown>,
  request?: Record<string, unknown>,
): ChatRequestPayload {
  const retry = {
    ...payload,
    ...(location ? { current_location: location } : {}),
    ...(request ? { location_request: request } : {}),
    _location_retry: true,
  }
  delete retry.client_message
  return retry
}

export interface StreamMessagePatch {
  delta?: string
  reset?: boolean
  complete?: boolean
  error?: string
  status?: { name: string; phase: 'active' | 'complete' }
  searchResults?: SearchMeta
  workspaceAction?: WorkspaceAction
  clarification?: ClarificationPrompt
  followUps?: string[]
  papers?: PaperInfo[]
  requestLocation?: boolean
}

/** Convert the shared Agent SSE protocol into platform-neutral UI patches. */
export function streamEventPatch(event: FlorisStreamEvent): StreamMessagePatch | null {
  switch (event.type) {
    case 'ai_response':
      return { delta: typeof event.content === 'string' ? event.content : '' }
    case 'ai_response_reset':
      return { reset: true }
    case 'answer_complete':
      return { complete: true }
    case 'error_message':
      return { error: String(event.content || event.message || '') }
    case 'tool_call':
      return event.name ? { status: { name: String(event.name), phase: 'active' } } : null
    case 'tool_result':
      return event.name ? { status: { name: String(event.name), phase: 'complete' } } : null
    case 'search_results':
    case 'search_media':
      return { searchResults: (event.payload || {}) as SearchMeta }
    case 'map_action':
    case 'calendar_action':
    case 'side_effect_action': {
      const action = event.payload?.action as WorkspaceAction | undefined
      return action ? { workspaceAction: action } : null
    }
    case 'clarification_action': {
      const clarification = event.payload?.clarification as ClarificationPrompt | undefined
      return clarification ? { clarification } : null
    }
    case 'follow_ups':
      return {
        followUps: Array.isArray(event.payload?.items)
          ? event.payload.items.map(String).filter(Boolean).slice(0, 3)
          : [],
      }
    case 'paper_results': {
      const value = event.payload as unknown
      const papers = Array.isArray(value)
        ? value
        : Array.isArray((value as { papers?: unknown[] } | undefined)?.papers)
          ? (value as { papers: PaperInfo[] }).papers
          : []
      return { papers: papers as PaperInfo[] }
    }
    case 'browser_location_request':
      return { requestLocation: true }
    default:
      return null
  }
}
