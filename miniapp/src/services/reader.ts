import { startChunkedSse, type ChunkedSseTask } from './stream'

export type ReaderAction = 'translate' | 'summarize' | 'explain' | 'formula' | 'analyze' | 'terms' | 'qa'

export function startReaderStream(
  conversationId: string,
  action: ReaderAction,
  text: string,
  question: string,
  responseLanguage: string,
  callbacks: {
    onDelta: (value: string) => void
    onDone: () => void
    onError: (value: string) => void
  },
): Promise<ChunkedSseTask> {
  let settled = false
  const done = () => {
    if (settled) return
    settled = true
    callbacks.onDone()
  }
  const fail = (message: string) => {
    if (settled) return
    settled = true
    callbacks.onError(message)
  }

  return startChunkedSse({
    path: '/reader',
    conversationId,
    data: {
      action,
      text,
      ...(question ? { question } : {}),
      response_language: responseLanguage,
    },
    onFrame(frame) {
      try {
        const event = JSON.parse(frame) as { type?: string; content?: string }
        if (event.type === 'paper_delta' && event.content && !settled) callbacks.onDelta(event.content)
        if (event.type === 'error_message') fail(event.content || '助读失败，请重试')
        if (event.type === 'paper_done') done()
      } catch {
        // Ignore malformed heartbeats.
      }
    },
    onDone: done,
    onError: fail,
  })
}
