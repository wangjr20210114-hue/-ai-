import { describe, expect, it, vi } from 'vitest'

vi.mock('./request', () => ({
  apiRequest: vi.fn(),
}))

import { activeProactiveNotifications } from './proactive'

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
})
