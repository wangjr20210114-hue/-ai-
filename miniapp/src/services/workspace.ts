import type { WorkspaceAction } from '@floris/contracts'
import { apiRequest } from './request'

export interface WorkspaceResponse {
  revision: number
  schedules?: Array<Record<string, unknown>>
  map?: {
    action_id: string
    title: string
    places: Array<Record<string, unknown>>
    route_mode?: string
    route_strategy?: string
    show_route?: boolean
  } | null
  action?: WorkspaceAction
}

export function workspaceOperation(
  conversationId: string,
  operation: string,
  input: Record<string, unknown> = {},
): Promise<WorkspaceResponse> {
  return apiRequest<WorkspaceResponse>('/workspace', {
    method: 'POST',
    conversationId,
    data: { operation, ...input },
    timeout: operation === 'confirm_action' ? 120_000 : 30_000,
  })
}
