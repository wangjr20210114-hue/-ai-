import Taro from '@tarojs/taro'
import { apiUrl } from './config'
import { ensureSession } from './session'

export interface ApiRequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE'
  data?: unknown
  conversationId?: string
  timeout?: number
}

export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
  retryAuth = true,
): Promise<T> {
  const session = await ensureSession()
  const response = await Taro.request<T & { error?: string }>({
    url: apiUrl(path),
    method: options.method || 'GET',
    data: options.data,
    timeout: options.timeout || 30_000,
    header: {
      'content-type': 'application/json',
      Authorization: `Bearer ${session.token}`,
      ...(options.conversationId ? { 'makers-conversation-id': options.conversationId } : {}),
    },
  })
  if (response.statusCode === 401 && retryAuth) {
    await ensureSession(true)
    return apiRequest<T>(path, options, false)
  }
  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw new Error(response.data?.error || `请求失败（${response.statusCode}）`)
  }
  return response.data
}
