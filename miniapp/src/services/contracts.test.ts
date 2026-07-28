import { describe, expect, it } from 'vitest'
import {
  createChatPayload,
  createClarificationPayload,
  createConversationId,
  createLocationRetryPayload,
  imageVersionsFrom,
  mergeMessages,
  restoredConversationWasInterrupted,
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

  it('restores a structured card without falsely reporting an interrupted run', () => {
    const restored: ChatMessage[] = [
      { id: 'u1', role: 'user', content: '写入日程', ts: 1 },
      {
        id: 'a1',
        role: 'ai',
        content: '',
        ts: 2,
        clarification: { id: 'c1', title: '时间', prompt: '请选择', fields: [] },
      },
    ]
    expect(restoredConversationWasInterrupted(mergeMessages(restored, []), true)).toBe(false)
  })

  it('drops the optimistic user-only cache tail when Makers has not completed it', () => {
    const remote: ChatMessage[] = [
      { id: 'u1', role: 'user', content: '第一问', ts: 1 },
      { id: 'a1', role: 'ai', content: '第一答', ts: 2 },
    ]
    const local: ChatMessage[] = [
      ...remote,
      { id: 'u2', role: 'user', content: '未完成的第二问', ts: Date.now() },
    ]
    expect(mergeMessages(remote, local).map(({ id, content }) => ({ id, content }))).toEqual(
      remote.map(({ id, content }) => ({ id, content })),
    )
  })

  it('retries location inside the same turn without resending the user message', () => {
    const original = createChatPayload(
      { id: 'u1', role: 'user', content: '附近有什么餐厅', ts: 1 },
      'zh-CN',
    )
    const retry = createLocationRetryPayload(
      original,
      { latitude: 39.9, longitude: 116.4 },
      { permission: 'granted' },
    )
    expect(retry.client_message).toBeUndefined()
    expect(retry._location_retry).toBe(true)
    expect(retry.current_location).toMatchObject({ latitude: 39.9 })
  })

  it('reuses the Makers image version chain and falls back to one result image', () => {
    expect(imageVersionsFrom({
      id: 'image-2',
      payload: { prompt: '橘猫' },
      result: {
        image_url: '/files?key=latest',
        versions: [
          { id: 'image-1', prompt: '橘猫', image_url: '/files?key=first' },
          { id: 'image-2', prompt: '加蓝围巾', image_url: '/files?key=latest' },
        ],
      },
    }).map((item) => item.id)).toEqual(['image-1', 'image-2'])
    expect(imageVersionsFrom({
      id: 'image-1',
      payload: { prompt: '橘猫' },
      result: { image_url: '/files?key=first' },
    })[0]).toMatchObject({ id: 'image-1', prompt: '橘猫' })
  })
})
