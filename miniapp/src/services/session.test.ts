import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getStorageSync: vi.fn(),
  setStorageSync: vi.fn(),
  removeStorageSync: vi.fn(),
  login: vi.fn(),
  request: vi.fn(),
}))

vi.mock('@tarojs/taro', () => ({
  default: {
    getStorageSync: mocks.getStorageSync,
    setStorageSync: mocks.setStorageSync,
    removeStorageSync: mocks.removeStorageSync,
    login: mocks.login,
    request: mocks.request,
  },
}))

import { ensureSession } from './session'

describe('native WeChat login session', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getStorageSync.mockReturnValue(null)
    mocks.login.mockResolvedValue({ code: 'one-time-wx-code' })
    mocks.request.mockResolvedValue({
      statusCode: 200,
      data: {
        token: 'signed-miniapp-session',
        expires_at: Date.now() + 3_600_000,
        user_id: 'wx-user-hash',
        conversation_prefix: 'yb7_wxuser_',
      },
    })
  })

  it('exchanges only the one-time wx.login code and persists the signed Makers session', async () => {
    await expect(ensureSession()).resolves.toMatchObject({
      token: 'signed-miniapp-session',
      userId: 'wx-user-hash',
      conversationPrefix: 'yb7_wxuser_',
    })

    expect(mocks.login).toHaveBeenCalledTimes(1)
    expect(mocks.request).toHaveBeenCalledWith(expect.objectContaining({
      method: 'POST',
      data: { code: 'one-time-wx-code' },
    }))
    expect(JSON.stringify(mocks.request.mock.calls[0][0])).not.toMatch(/secret|openid|session_key/i)
    expect(mocks.setStorageSync).toHaveBeenCalledWith(
      'floris.miniapp.session.v1',
      expect.objectContaining({ token: 'signed-miniapp-session' }),
    )
  })
})
