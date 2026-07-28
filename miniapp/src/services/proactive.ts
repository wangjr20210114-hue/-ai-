import { apiRequest } from './request'
import { translate } from '@/i18n'

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

export type ProactivePreferences = {
  enabled?: boolean
  lookahead_hours?: number
  provider_schedule_limit?: number
  route_gap_hours?: number
  travel_buffer_minutes?: number
  quiet_hours?: { enabled?: boolean; start?: string; end?: string }
  fallback_mottos?: string[]
}

export type ProactiveWorkflowStep = {
  id: string
  title?: string
  body?: string
  action_prompt?: string
  status: 'pending' | 'notified' | 'completed' | 'skipped' | 'failed' | 'attention_required' | 'compensating' | 'compensated'
  due_at?: number | null
  last_error?: string
}

export type ProactiveWorkflow = {
  id: string
  title: string
  reason?: string
  status: 'awaiting_confirmation' | 'active' | 'completed' | 'rejected' | 'cancelled'
  version: number
  steps: ProactiveWorkflowStep[]
  created_at?: number
  updated_at?: number
}

export type ProactiveState = {
  notifications?: ProactiveNotification[]
  preferences?: ProactivePreferences
  workflows?: ProactiveWorkflow[]
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

export function actionableProactiveWorkflows(items: ProactiveWorkflow[]): ProactiveWorkflow[] {
  return items.filter((item) => (
    item.status === 'awaiting_confirmation' || item.status === 'active'
  ))
}

export function currentWorkflowStep(
  workflow: ProactiveWorkflow,
): ProactiveWorkflowStep | undefined {
  return workflow.steps.find((item) => (
    !['completed', 'skipped', 'compensated'].includes(item.status)
  ))
}

export function proactiveWorkflowHeadline(items: ProactiveWorkflow[]): string {
  const workflows = actionableProactiveWorkflows(items)
  const workflow = workflows.find((item) => item.status === 'awaiting_confirmation') || workflows[0]
  if (!workflow) return ''
  if (workflow.status === 'awaiting_confirmation') {
    return translate('workflowProposalHeadline', { title: workflow.title })
  }
  const step = currentWorkflowStep(workflow)
  return step?.title
    ? translate('workflowActiveStep', { title: workflow.title, step: step.title })
    : translate('workflowActive', { title: workflow.title })
}

export function proactiveTickerLines(state: ProactiveState, limit = 10): string[] {
  const workflow = proactiveWorkflowHeadline(state.workflows || [])
  const reminders = activeProactiveNotifications(state.notifications || [])
    .map((item) => String(item.body || item.title || '').trim())
    .filter(Boolean)
  const realLines = [workflow, ...reminders].filter(Boolean)
  if (realLines.length) return [...new Set(realLines)].slice(0, limit)
  return [...new Set(
    (state.preferences?.fallback_mottos || [])
      .map((item) => String(item || '').trim())
      .filter(Boolean),
  )].slice(0, limit)
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
