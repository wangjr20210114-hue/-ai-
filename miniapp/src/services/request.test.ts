import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  request: vi.fn(),
  ensureSession: vi.fn(),
}))

vi.mock('@tarojs/taro', () => ({
  default: {
    request: mocks.request,
  },
}))

vi.mock('./session', () => ({
  ensureSession: mocks.ensureSession,
}))

import { apiRequest } from './request'

describe('authenticated Makers request adapter', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.ensureSession.mockResolvedValue({
      token: 'renewed-token',
      conversationPrefix: 'yb7_1234567890_',
    })
  })

  it('renews wx.login session once after a 401 and preserves the request', async () => {
    mocks.request
      .mockResolvedValueOnce({ statusCode: 401, data: { error: 'Unauthorized' } })
      .mockResolvedValueOnce({ statusCode: 200, data: { ok: true } })

    await expect(apiRequest<{ ok: boolean }>('/workspace', {
      method: 'POST',
      conversationId: 'yb7_1234567890_test',
      data: { operation: 'get' },
    })).resolves.toEqual({ ok: true })

    expect(mocks.ensureSession.mock.calls.some(([force]) => force === true)).toBe(true)
    expect(mocks.request).toHaveBeenCalledTimes(2)
    expect(mocks.request.mock.calls[1][0]).toMatchObject({
      method: 'POST',
      data: { operation: 'get' },
      header: {
        Authorization: 'Bearer renewed-token',
        'makers-conversation-id': 'yb7_1234567890_test',
      },
    })
  })

  it('does not retry ordinary provider or validation failures', async () => {
    mocks.request.mockResolvedValue({
      statusCode: 422,
      data: { error: '日程参数无效' },
    })

    await expect(apiRequest('/workspace', {
      method: 'POST',
      data: { operation: 'confirm_action' },
    })).rejects.toThrow('日程参数无效')
    expect(mocks.request).toHaveBeenCalledTimes(1)
  })
})
