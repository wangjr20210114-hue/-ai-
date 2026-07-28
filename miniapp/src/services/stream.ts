import 'fast-text-encoding'
import Taro from '@tarojs/taro'
import { splitSseFrames } from '@floris/contracts'
import { apiUrl } from './config'
import { ensureSession } from './session'

export interface ChunkedSseOptions {
  path: string
  conversationId: string
  data: unknown
  timeout?: number
  onFrame: (frame: string) => void
  onDone: () => void
  onError: (message: string) => void
}

export interface ChunkedSseTask {
  abort: () => void
}

/** One native WeChat chunked-request adapter shared by chat and paper reader. */
export async function startChunkedSse(options: ChunkedSseOptions): Promise<ChunkedSseTask> {
  const session = await ensureSession()
  const decoder = new TextDecoder()
  let buffer = ''
  let receivedChunk = false
  let protocolDone = false
  let aborted = false
  let settled = false

  const finish = () => {
    if (settled) return
    settled = true
    options.onDone()
  }
  const fail = (message: string) => {
    if (settled || aborted) return
    options.onError(message)
    finish()
  }
  const consume = (chunk: ArrayBuffer, final = false) => {
    buffer += decoder.decode(chunk, { stream: !final })
    const parsed = splitSseFrames(buffer)
    buffer = parsed.rest
    parsed.frames.forEach((frame) => {
      if (frame === '[DONE]') {
        protocolDone = true
        finish()
      } else {
        options.onFrame(frame)
      }
    })
  }

  const task = Taro.request({
    url: apiUrl(options.path),
    method: 'POST',
    timeout: options.timeout || 180_000,
    enableChunked: true,
    responseType: 'arraybuffer',
    header: {
      'content-type': 'application/json',
      Accept: 'text/event-stream',
      'x-floris-client': 'wechat-miniapp',
      Authorization: `Bearer ${session.token}`,
      'makers-conversation-id': options.conversationId,
    },
    data: options.data,
    success(response) {
      if (response.statusCode === 401) return fail('登录状态已失效，请重新发送')
      if (response.statusCode < 200 || response.statusCode >= 300) {
        return fail(`请求失败（${response.statusCode}），请重试`)
      }
      if (!receivedChunk && !protocolDone && response.data instanceof ArrayBuffer && response.data.byteLength) {
        consume(response.data, true)
      }
      if (!protocolDone) fail('网络连接提前结束，请点击重试')
    },
    fail(error) {
      if (!aborted) fail(String(error.errMsg || '网络请求失败，请重试'))
    },
  })
  task.onChunkReceived(({ data }) => {
    receivedChunk = true
    consume(data)
  })
  return {
    abort() {
      aborted = true
      task.abort()
      finish()
    },
  }
}
