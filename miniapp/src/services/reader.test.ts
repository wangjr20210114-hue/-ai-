import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  startChunkedSse: vi.fn(),
}))

vi.mock('./stream', () => ({
  startChunkedSse: mocks.startChunkedSse,
}))

import { startReaderStream } from './reader'

describe('native paper reader stream', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.startChunkedSse.mockResolvedValue({ abort: vi.fn() })
  })

  it('reuses the Reader Agent protocol and settles exactly once', async () => {
    const onDelta = vi.fn()
    const onDone = vi.fn()
    const onError = vi.fn()

    await startReaderStream(
      'yb7_reader',
      'translate',
      'source text',
      '',
      'zh-CN',
      { onDelta, onDone, onError },
    )

    const options = mocks.startChunkedSse.mock.calls[0][0]
    expect(options).toMatchObject({
      path: '/reader',
      conversationId: 'yb7_reader',
      data: {
        action: 'translate',
        text: 'source text',
        response_language: 'zh-CN',
      },
    })

    options.onFrame(JSON.stringify({ type: 'paper_delta', content: '译文' }))
    options.onFrame(JSON.stringify({ type: 'paper_done' }))
    options.onDone()

    expect(onDelta).toHaveBeenCalledWith('译文')
    expect(onDone).toHaveBeenCalledTimes(1)
    expect(onError).not.toHaveBeenCalled()
  })

  it('does not convert an Agent error followed by transport close into a second completion', async () => {
    const onDelta = vi.fn()
    const onDone = vi.fn()
    const onError = vi.fn()

    await startReaderStream(
      'yb7_reader',
      'qa',
      'source text',
      'what?',
      'en-US',
      { onDelta, onDone, onError },
    )

    const options = mocks.startChunkedSse.mock.calls[0][0]
    options.onFrame(JSON.stringify({ type: 'error_message', content: '暂时无法阅读' }))
    options.onDone()
    options.onError('网络连接提前结束')
    options.onFrame(JSON.stringify({ type: 'paper_delta', content: 'late text' }))

    expect(onError).toHaveBeenCalledTimes(1)
    expect(onError).toHaveBeenCalledWith('暂时无法阅读')
    expect(onDone).not.toHaveBeenCalled()
    expect(onDelta).not.toHaveBeenCalled()
  })
})
