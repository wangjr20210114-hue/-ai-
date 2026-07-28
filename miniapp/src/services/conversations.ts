import Taro from '@tarojs/taro'
import { createConversationId, type ChatMessage, type MiniappSession } from '@floris/contracts'
import { apiRequest } from './request'

const ACTIVE_CONVERSATION_KEY = 'floris.miniapp.active-conversation.v1'
const messageKey = (id: string) => `floris.miniapp.messages.${id}`

export interface ConversationSummary {
  id: string
  title: string
  updatedAt: number
  messageCount: number
}

export interface BootstrapData {
  messages?: ChatMessage[]
  schedules?: Array<Record<string, unknown>>
  map_places?: Array<Record<string, unknown>>
  map_title?: string
  map_show_route?: boolean
  map_route_mode?: string
  run?: { status?: string; run_id?: string }
}

export function getOrCreateConversationId(session: MiniappSession): string {
  const cached = String(Taro.getStorageSync(ACTIVE_CONVERSATION_KEY) || '')
  if (cached.startsWith(session.conversationPrefix)) return cached
  const created = createConversationId(session.conversationPrefix)
  Taro.setStorageSync(ACTIVE_CONVERSATION_KEY, created)
  return created
}

export function setActiveConversationId(id: string): void {
  Taro.setStorageSync(ACTIVE_CONVERSATION_KEY, id)
}

export function newConversation(session: MiniappSession): string {
  const id = createConversationId(session.conversationPrefix)
  setActiveConversationId(id)
  return id
}

export function readCachedMessages(conversationId: string): ChatMessage[] {
  try {
    const value = Taro.getStorageSync<ChatMessage[]>(messageKey(conversationId))
    return Array.isArray(value)
      ? value.filter((item) => item?.id && item?.role).map((item) => ({ ...item, streaming: false }))
      : []
  } catch {
    return []
  }
}

export function cacheMessages(conversationId: string, messages: ChatMessage[]): void {
  Taro.setStorageSync(
    messageKey(conversationId),
    messages.filter((item) => !item.streaming && !item.failed).slice(-60),
  )
}

export async function bootstrap(conversationId: string): Promise<BootstrapData> {
  return apiRequest<BootstrapData>('/messages', {
    method: 'POST',
    conversationId,
    data: { conversation_id: conversationId },
    timeout: 12_000,
  })
}

export async function listConversations(): Promise<ConversationSummary[]> {
  const result = await apiRequest<{ conversations?: Array<Record<string, unknown>> }>('/conversations')
  return (result.conversations || []).map((item) => {
    const metadata = item.metadata && typeof item.metadata === 'object'
      ? item.metadata as Record<string, unknown>
      : {}
    return {
      id: String(item.conversationId || ''),
      title: String(metadata.title || '新对话'),
      updatedAt: Number(item.lastMessageAt || item.createdAt || Date.now()),
      messageCount: Number(item.messageCount || 0),
    }
  }).filter((item) => item.id)
}
