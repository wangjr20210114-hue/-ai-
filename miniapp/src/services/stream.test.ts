import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

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

import { startChunkedSse } from './stream'

type RequestOptions = {
  success: (response: { statusCode: number; data: ArrayBuffer }) => void
  fail: (error: { errMsg?: string }) => void
  header: Record<string, string>
  enableChunked: boolean
}

function bytes(value: string): ArrayBuffer {
  const encoded = new TextEncoder().encode(value)
  return encoded.buffer.slice(encoded.byteOffset, encoded.byteOffset + encoded.byteLength)
}

describe('native WeChat chunked SSE adapter', () => {
  let options: RequestOptions
  let onChunk: (event: { data: ArrayBuffer }) => void
  let abort: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.clearAllMocks()
    abort = vi.fn()
    mocks.ensureSession.mockResolvedValue({ token: 'signed-session' })
    mocks.request.mockImplementation((value: RequestOptions) => {
      options = value
      return {
        abort,
        onChunkReceived(callback: typeof onChunk) {
          onChunk = callback
        },
      }
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('reassembles UTF-8 and SSE frames arriving across native chunks', async () => {
    // Match the real WeChat runtime: the browser TextDecoder global is absent.
    vi.stubGlobal('TextDecoder', undefined)
    const frames: string[] = []
    const done = vi.fn()
    const error = vi.fn()
    await startChunkedSse({
      path: '/chat',
      conversationId: 'yb7_1234567890_test',
      data: { text: '你好' },
      onFrame: (frame) => frames.push(frame),
      onDone: done,
      onError: error,
    })

    const wire = 'data: {"type":"ai_response","content":"你好🐈"}\n\ndata: [DONE]\n\n'
    const encoded = new TextEncoder().encode(wire)
    const splitAt = encoded.indexOf(0xe5) + 1
    const emojiSplit = encoded.indexOf(0xf0) + 2
    onChunk({ data: encoded.slice(0, splitAt).buffer })
    onChunk({ data: encoded.slice(splitAt, emojiSplit).buffer })
    onChunk({ data: encoded.slice(emojiSplit).buffer })
    options.success({ statusCode: 200, data: new ArrayBuffer(0) })

    expect(options.enableChunked).toBe(true)
    expect(options.header.Authorization).toBe('Bearer signed-session')
    expect(frames).toEqual(['{"type":"ai_response","content":"你好🐈"}'])
    expect(error).not.toHaveBeenCalled()
    expect(done).toHaveBeenCalledTimes(1)
  })

  it('turns a premature transport close into one actionable error', async () => {
    const error = vi.fn()
    const done = vi.fn()
    await startChunkedSse({
      path: '/chat',
      conversationId: 'yb7_1234567890_test',
      data: {},
      onFrame: vi.fn(),
      onDone: done,
      onError: error,
    })

    onChunk({ data: bytes('data: {"type":"ai_response","content":"半句"}\n\n') })
    options.success({ statusCode: 200, data: new ArrayBuffer(0) })

    expect(error).toHaveBeenCalledWith('网络连接提前结束，请点击重试')
    expect(done).toHaveBeenCalledTimes(1)
  })

  it('aborts locally without reporting a network failure or restarting', async () => {
    const error = vi.fn()
    const done = vi.fn()
    const task = await startChunkedSse({
      path: '/chat',
      conversationId: 'yb7_1234567890_test',
      data: {},
      onFrame: vi.fn(),
      onDone: done,
      onError: error,
    })

    task.abort()
    options.fail({ errMsg: 'request:fail abort' })

    expect(abort).toHaveBeenCalledTimes(1)
    expect(error).not.toHaveBeenCalled()
    expect(done).toHaveBeenCalledTimes(1)
    expect(mocks.request).toHaveBeenCalledTimes(1)
  })
})
