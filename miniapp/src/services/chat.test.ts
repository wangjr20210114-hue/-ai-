import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  storage: new Map<string, unknown>(),
  startChunkedSse: vi.fn(),
  apiRequest: vi.fn(),
}))

vi.mock('@tarojs/taro', () => ({
  default: {
    getStorageSync: (key: string) => mocks.storage.get(key),
    setStorageSync: (key: string, value: unknown) => mocks.storage.set(key, value),
    removeStorageSync: (key: string) => mocks.storage.delete(key),
  },
}))

vi.mock('./stream', () => ({
  startChunkedSse: mocks.startChunkedSse,
}))

vi.mock('./request', () => ({
  apiRequest: mocks.apiRequest,
}))

import { applyClarificationPatch, startChatStream } from './chat'

describe('clarification continuation state', () => {
  it('unlocks a later clarification while preserving the state of the same card', () => {
    const message = {
      id: 'assistant-1',
      role: 'ai' as const,
      content: '',
      ts: 1,
      clarificationAnswered: true,
      clarification: {
        id: 'clarification-1',
        title: '出发时间',
        prompt: '请选择',
        fields: [],
      },
    }
    const same = applyClarificationPatch(message, message.clarification)
    expect(same.clarificationAnswered).toBe(true)

    const next = applyClarificationPatch(message, {
      id: 'clarification-2',
      title: '具体酒店',
      prompt: '请选择',
      fields: [],
    })
    expect(next.clarification?.id).toBe('clarification-2')
    expect(next.clarificationAnswered).toBe(false)
  })
})

describe('chat stop ownership', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.storage.clear()
    mocks.apiRequest.mockResolvedValue({ status: 'cancelled' })
    mocks.startChunkedSse.mockResolvedValue({ abort: vi.fn() })
  })

  it('marks an explicit stop and allows only the next deliberate send', async () => {
    const callbacks = {
      onPatch: vi.fn(),
      onDone: vi.fn(),
      onError: vi.fn(),
    }
    const first = await startChatStream(
      'yb7_1234567890_test',
      {
        activity: 'asked',
        text: '第一问',
        message_id: 'u1',
        client_message_id: 'u1',
        reference_images: [],
        response_language: 'zh-CN',
      },
      callbacks,
    )
    await first.stop()

    expect(mocks.apiRequest).toHaveBeenCalledWith('/stop', expect.objectContaining({
      data: { conversation_id: 'yb7_1234567890_test' },
      conversationId: expect.stringMatching(/^floris-stop-[0-9a-z]+$/),
    }))
    expect(mocks.apiRequest.mock.calls[0][1].conversationId).not.toBe('yb7_1234567890_test')
    expect(mocks.storage.get('floris.miniapp.manual-stop.yb7_1234567890_test')).toEqual({
      state: 'confirmed',
    })

    await startChatStream(
      'yb7_1234567890_test',
      {
        activity: 'asked',
        text: '新的问题',
        message_id: 'u2',
        client_message_id: 'u2',
        reference_images: [],
        response_language: 'zh-CN',
      },
      callbacks,
    )
    expect(mocks.apiRequest).toHaveBeenCalledTimes(1)
    expect(mocks.startChunkedSse.mock.calls[1][0].data).toMatchObject({
      text: '新的问题',
      _allow_after_stop: true,
    })
    expect(mocks.storage.has('floris.miniapp.manual-stop.yb7_1234567890_test')).toBe(false)

    await startChatStream(
      'yb7_1234567890_test',
      {
        activity: 'asked',
        text: '再问一次',
        message_id: 'u3',
        client_message_id: 'u3',
        reference_images: [],
        response_language: 'zh-CN',
      },
      callbacks,
    )
    expect(mocks.startChunkedSse.mock.calls[2][0].data._allow_after_stop).toBeUndefined()
  })

  it('does not start a new model run until Makers confirms the prior stop', async () => {
    mocks.storage.set('floris.miniapp.manual-stop.yb7_stop_barrier', { state: 'pending' })
    mocks.apiRequest.mockRejectedValueOnce(new Error('offline'))

    await expect(startChatStream(
      'yb7_stop_barrier',
      {
        activity: 'asked',
        text: '新的问题',
        message_id: 'u2',
        client_message_id: 'u2',
        reference_images: [],
        response_language: 'zh-CN',
      },
      {
        onPatch: vi.fn(),
        onDone: vi.fn(),
        onError: vi.fn(),
      },
    )).rejects.toThrow('上一次生成还在停止')

    expect(mocks.startChunkedSse).not.toHaveBeenCalled()
    expect(mocks.storage.get('floris.miniapp.manual-stop.yb7_stop_barrier')).toEqual({
      state: 'pending',
    })
  })

  it('waits for Makers to turn cancel-requested into a confirmed stop', async () => {
    mocks.storage.set('floris.miniapp.manual-stop.yb7_cancelling', { state: 'pending' })
    mocks.apiRequest.mockResolvedValueOnce({ status: 'cancel_requested' })

    await startChatStream(
      'yb7_cancelling',
      {
        activity: 'asked',
        text: '下一问',
        message_id: 'u2',
        client_message_id: 'u2',
        reference_images: [],
        response_language: 'zh-CN',
      },
      {
        onPatch: vi.fn(),
        onDone: vi.fn(),
        onError: vi.fn(),
      },
    )

    expect(mocks.apiRequest).toHaveBeenCalledTimes(2)
    expect(mocks.startChunkedSse).toHaveBeenCalledTimes(1)
    expect(mocks.storage.has('floris.miniapp.manual-stop.yb7_cancelling')).toBe(false)
  })

  it('retries an unconfirmed stop once before starting the next deliberate run', async () => {
    mocks.storage.set('floris.miniapp.manual-stop.yb7_pending_stop', { state: 'pending' })

    await startChatStream(
      'yb7_pending_stop',
      {
        activity: 'asked',
        text: '继续下一问',
        message_id: 'u2',
        client_message_id: 'u2',
        reference_images: [],
        response_language: 'zh-CN',
      },
      {
        onPatch: vi.fn(),
        onDone: vi.fn(),
        onError: vi.fn(),
      },
    )

    expect(mocks.apiRequest).toHaveBeenCalledTimes(1)
    expect(mocks.startChunkedSse).toHaveBeenCalledTimes(1)
    expect(mocks.startChunkedSse.mock.calls[0][0].data._allow_after_stop).toBe(true)
    expect(mocks.storage.has('floris.miniapp.manual-stop.yb7_pending_stop')).toBe(false)
  })

  it('keeps compatibility with the boolean marker written by 0.6.0', async () => {
    mocks.storage.set('floris.miniapp.manual-stop.yb7_legacy_stop', true)

    await startChatStream(
      'yb7_legacy_stop',
      {
        activity: 'asked',
        text: '升级后的下一问',
        message_id: 'u2',
        client_message_id: 'u2',
        reference_images: [],
        response_language: 'zh-CN',
      },
      {
        onPatch: vi.fn(),
        onDone: vi.fn(),
        onError: vi.fn(),
      },
    )

    expect(mocks.apiRequest).toHaveBeenCalledTimes(1)
    expect(mocks.startChunkedSse.mock.calls[0][0].data._allow_after_stop).toBe(true)
  })
})
