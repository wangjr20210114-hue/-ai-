import { describe, expect, it } from 'vitest'
import {
  createChatPayload,
  createClarificationPayload,
  createConversationId,
  splitSseFrames,
  streamEventPatch,
  type ChatMessage,
  type ClarificationPrompt,
} from '@floris/contracts'

describe('shared Floris protocol', () => {
  it('parses split SSE frames and keeps a partial tail', () => {
    const parsed = splitSseFrames('data: {"type":"ai_response","content":"你"}\n\ndata: {"type":"ai_')
    expect(parsed.frames).toEqual(['{"type":"ai_response","content":"你"}'])
    expect(parsed.rest).toBe('data: {"type":"ai_')
  })

  it('builds a miniapp conversation id inside the signed user prefix', () => {
    const id = createConversationId('yb7_1234567890_', 1_000, () => 0.25)
    expect(id).toMatch(/^yb7_1234567890_[0-9A-Za-z]+$/)
    expect(id.length).toBeLessThanOrEqual(36)
  })

  it('reuses the same chat payload contract as the web client', () => {
    const message: ChatMessage = { id: 'u1', role: 'user', content: '你好', ts: 1 }
    expect(createChatPayload(message, 'zh-CN')).toMatchObject({
      activity: 'asked',
      text: '你好',
      client_message_id: 'u1',
      client_message: message,
      response_language: 'zh-CN',
    })
  })

  it('submits structured answers as a silent clarification continuation', () => {
    const prompt: ClarificationPrompt = {
      id: 'clarify-1',
      title: '选择地点',
      prompt: '请选择',
      fields: [{
        id: 'place',
        label: '目的地',
        type: 'single',
        required: true,
        options: ['天安门'],
        option_values: { 天安门: 'poi-123' },
      }],
    }
    const payload = createClarificationPayload(prompt, { place: '天安门' }, 'ai-1', 'zh-CN')
    expect(payload.client_message).toBeUndefined()
    expect(payload.clarification_response?.answers[0].value).toBe('poi-123')
  })

  it('maps Agent events without embedding business intent in the miniapp', () => {
    expect(streamEventPatch({ type: 'ai_response', content: '答案' })).toEqual({ delta: '答案' })
    expect(streamEventPatch({
      type: 'clarification_action',
      payload: { clarification: { id: 'c', title: '补充', prompt: '请选择', fields: [] } },
    })?.clarification?.id).toBe('c')
  })
})
