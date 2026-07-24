import { describe, expect, it } from 'vitest';
import { activeProactiveNotifications, proactiveFallbackLines, proactiveReminderLines } from './proactiveNotifications';
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

describe('proactiveReminderLines', () => {
  it('turns weather evidence into a natural local reminder', () => {
    const lines = proactiveReminderLines([
      notification('weather', {
        type: 'weather_risk',
        title: '天气提醒',
        body: '天气可能影响今天的安排',
        evidence: {
          weather: {
            district: '海淀区',
            weather: '雷阵雨',
          },
        },
      }),
    ]);

    expect(lines.map((item) => item.text)).toEqual([
      '今天海淀区有雷阵雨，记得带伞，也注意保暖。',
    ]);
  });

  it('keeps separate opportunities as separate rotating sentences', () => {
    const lines = proactiveReminderLines([
      notification('schedule', { body: '下午三点有产品评审，建议提前十分钟准备。' }),
      notification('memory', { body: '你最近常问 AI 新闻，今天有新进展可以看看。' }),
    ]);

    expect(lines).toHaveLength(2);
    expect(lines.map((item) => item.notificationId)).toEqual(['schedule', 'memory']);
    expect(lines.every((item) => item.text.endsWith('。'))).toBe(true);
  });
});

describe('proactiveFallbackLines', () => {
  it('keeps at most five unique, non-empty presentation fallbacks', () => {
    const lines = proactiveFallbackLines([' 星光会找到夜路。 ', '', '星光会找到夜路。', '二', '三', '四', '五', '六']);
    expect(lines.map((item) => item.text)).toEqual(['星光会找到夜路。', '二', '三', '四', '五']);
    expect(lines.every((item) => item.notificationId === '')).toBe(true);
  });
});
