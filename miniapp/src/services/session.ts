import Taro from '@tarojs/taro'
import type { MiniappSession } from '@floris/contracts'
import { apiUrl } from './config'

const SESSION_KEY = 'floris.miniapp.session.v1'
const EXPIRY_MARGIN_MS = 5 * 60 * 1000
let activeLogin: Promise<MiniappSession> | null = null

export function readSession(): MiniappSession | null {
  try {
    const value = Taro.getStorageSync<MiniappSession>(SESSION_KEY)
    return value?.token && value.expiresAt > Date.now() + EXPIRY_MARGIN_MS ? value : null
  } catch {
    return null
  }
}

export function clearSession(): void {
  try { Taro.removeStorageSync(SESSION_KEY) } catch { /* no-op */ }
}

async function login(): Promise<MiniappSession> {
  const loginResult = await Taro.login()
  if (!loginResult.code) throw new Error('微信登录失败，请重试')
  const response = await Taro.request<{
    token?: string
    expires_at?: number
    user_id?: string
    conversation_prefix?: string
    error?: string
  }>({
    url: apiUrl('/wechat-auth'),
    method: 'POST',
    header: { 'content-type': 'application/json' },
    data: { code: loginResult.code },
  })
  const data = response.data || {}
  if (
    response.statusCode < 200
    || response.statusCode >= 300
    || !data.token
    || !data.expires_at
    || !data.user_id
    || !data.conversation_prefix
  ) {
    throw new Error(data.error || '微信登录失败，请重试')
  }
  const session: MiniappSession = {
    token: data.token,
    expiresAt: Number(data.expires_at),
    userId: data.user_id,
    conversationPrefix: data.conversation_prefix,
  }
  Taro.setStorageSync(SESSION_KEY, session)
  return session
}

export async function ensureSession(force = false): Promise<MiniappSession> {
  if (!force) {
    const existing = readSession()
    if (existing) return existing
  } else {
    clearSession()
  }
  if (!activeLogin) activeLogin = login().finally(() => { activeLogin = null })
  return activeLogin
}
