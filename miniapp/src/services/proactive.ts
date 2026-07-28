import { apiRequest } from './request'

export type ProactiveNotification = {
  id: string
  type?: string
  title?: string
  body?: string
  action_prompt?: string
  priority?: 'high' | 'normal' | 'low'
  status?: 'unread' | 'read' | 'snoozed' | 'dismissed'
  snoozed_until?: number | null
  created_at?: number
}

export type ProactiveState = {
  notifications?: ProactiveNotification[]
}

export function activeProactiveNotifications(
  items: ProactiveNotification[],
  now = Math.floor(Date.now() / 1000),
): ProactiveNotification[] {
  return items
    .filter((item) => (
      item.status === 'unread'
      || (item.status === 'snoozed' && Number(item.snoozed_until || 0) > now)
    ))
    .slice(0, 10)
}

export function proactiveOperation(
  conversationId: string,
  operation: string,
  input: Record<string, unknown> = {},
): Promise<ProactiveState> {
  return apiRequest<ProactiveState>('/proactive', {
    method: 'POST',
    conversationId,
    data: { operation, ...input },
    timeout: operation === 'get' ? 12_000 : 30_000,
  })
}
