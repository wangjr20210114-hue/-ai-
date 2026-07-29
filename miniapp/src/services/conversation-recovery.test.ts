import { describe, expect, it, vi } from 'vitest'

vi.mock('./conversations', () => ({
  bootstrap: vi.fn(),
}))

import {
  conversationRunActive,
  recoverConversation,
  recoveringMessages,
} from './conversation-recovery'

describe('Makers conversation recovery', () => {
  it('polls only the durable messages endpoint until the detached run completes', async () => {
    const read = vi.fn()
      .mockResolvedValueOnce({
        messages: [{ id: 'u1', role: 'user', content: '问题', ts: 1 }],
        run: { status: 'running', run_id: 'r1' },
      })
      .mockResolvedValueOnce({
        messages: [
          { id: 'u1', role: 'user', content: '问题', ts: 1 },
          { id: 'a1', role: 'ai', content: '答案', ts: 2 },
        ],
        run: { status: 'completed', run_id: 'r1' },
      })

    const result = await recoverConversation('yb7_recovery', {
      initial: {
        messages: [{ id: 'u1', role: 'user', content: '问题', ts: 1 }],
        run: { status: 'running', run_id: 'r1' },
      },
      cancelled: () => false,
      read,
      wait: async () => undefined,
    })

    expect(read).toHaveBeenCalledTimes(2)
    expect(result.timedOut).toBe(false)
    expect(result.data.messages?.at(-1)?.content).toBe('答案')
  })

  it('adds one streaming placeholder without inventing a second user message', () => {
    const messages = recoveringMessages(
      [{ id: 'u1', role: 'user', content: '问题', ts: 1 }],
      'recovering-r1',
    )
    expect(messages.map((message) => message.role)).toEqual(['user', 'ai'])
    expect(messages.at(-1)).toMatchObject({ id: 'recovering-r1', streaming: true })
  })

  it('recognizes only Makers non-terminal run states', () => {
    expect(conversationRunActive({ run: { status: 'running' } })).toBe(true)
    expect(conversationRunActive({ run: { status: 'cancel_requested' } })).toBe(true)
    expect(conversationRunActive({ run: { status: 'completed' } })).toBe(false)
    expect(conversationRunActive({ run: { status: 'failed' } })).toBe(false)
  })
})
