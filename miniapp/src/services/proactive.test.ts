import { describe, expect, it, vi } from 'vitest'

vi.mock('./request', () => ({
  apiRequest: vi.fn(),
}))

import {
  actionableProactiveWorkflows,
  activeProactiveNotifications,
  currentWorkflowStep,
  proactiveWorkflowHeadline,
} from './proactive'

describe('proactive reminder window', () => {
  it('shows unread and future snoozed reminders without reviving dismissed rows', () => {
    const now = 100
    const items = activeProactiveNotifications([
      { id: 'unread', status: 'unread', body: '出门带伞' },
      { id: 'future', status: 'snoozed', snoozed_until: 200, body: '稍后再说' },
      { id: 'expired', status: 'snoozed', snoozed_until: 99, body: '已到期' },
      { id: 'dismissed', status: 'dismissed', body: '不再提示' },
    ], now)
    expect(items.map((item) => item.id)).toEqual(['unread', 'future'])
  })

  it('reuses the existing Proactive Agent workflow lifecycle without client-side planning', () => {
    const workflows = actionableProactiveWorkflows([
      {
        id: 'proposal',
        title: '出发前准备',
        status: 'awaiting_confirmation',
        version: 1,
        steps: [],
      },
      {
        id: 'active',
        title: '今晚行程',
        status: 'active',
        version: 2,
        steps: [
          { id: 'done', status: 'completed', title: '准备材料' },
          { id: 'next', status: 'notified', title: '现在出发' },
        ],
      },
      {
        id: 'finished',
        title: '已完成',
        status: 'completed',
        version: 3,
        steps: [],
      },
    ])
    expect(workflows.map((item) => item.id)).toEqual(['proposal', 'active'])
    expect(currentWorkflowStep(workflows[1])?.id).toBe('next')
    expect(proactiveWorkflowHeadline(workflows)).toContain('待你确认')
    expect(proactiveWorkflowHeadline([workflows[1]])).toBe('“今晚行程”正在进行：现在出发')
  })
})
