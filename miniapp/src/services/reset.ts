import Taro from '@tarojs/taro'
import { apiRequest } from './request'

export interface ResetSummary {
  conversationsDeleted: number
  stateItemsDeleted: number
  filesDeleted: number
}

export async function resetApplicationData(
  conversationId: string,
  password: string,
): Promise<ResetSummary> {
  const inspect = await apiRequest<{ conversation_ids?: string[] }>('/reset-files', {
    method: 'POST',
    data: { password, operation: 'inspect' },
    timeout: 60_000,
  })
  const state = await apiRequest<{ state_items_deleted?: number }>('/reset', {
    method: 'POST',
    conversationId,
    data: {
      password,
      conversation_ids: inspect.conversation_ids || [],
    },
    timeout: 60_000,
  })
  const files = await apiRequest<{
    conversations_deleted?: number
    deleted?: Record<string, number>
  }>('/reset-files', {
    method: 'POST',
    data: { password, operation: 'clear' },
    timeout: 60_000,
  })
  return {
    conversationsDeleted: Number(files.conversations_deleted || 0),
    stateItemsDeleted: Number(state.state_items_deleted || 0),
    filesDeleted: Object.values(files.deleted || {})
      .reduce((total, value) => total + Number(value || 0), 0),
  }
}

export function clearMiniappLocalData(language: string): void {
  Taro.clearStorageSync()
  if (language) Taro.setStorageSync('floris-language', language)
}
