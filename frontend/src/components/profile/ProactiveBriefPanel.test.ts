import { describe, expect, it } from 'vitest';
import { activeProactiveNotifications } from './proactiveNotifications';
import type { ProactiveNotification } from '../../types';

function notification(id: string, patch: Partial<ProactiveNotification> = {}): ProactiveNotification {
  return {
    id, event_id: id, run_id: id, type: 'schedule_upcoming', title: id, body: id,
    reason: id, action_prompt: id, priority: 'normal', evidence: {}, status: 'unread',
    version: 1, created_at: 100, updated_at: 100, ...patch,
  };
}

describe('activeProactiveNotifications', () => {
  it('keeps only actionable fresh reminders and prioritizes high urgency', () => {
    const items = activeProactiveNotifications([
      notification('read', { status: 'read' }),
      notification('expired', { status: 'snoozed', snoozed_until: 99 }),
      notification('normal'),
      notification('high', { priority: 'high', updated_at: 90 }),
      notification('future', { status: 'snoozed', snoozed_until: 200 }),
    ], 100);
    expect(items.map((item) => item.id)).toEqual(['high', 'normal', 'future']);
  });
});
