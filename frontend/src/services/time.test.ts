import { describe, expect, it } from 'vitest';
import { formatConversationTime, normalizeTimestamp } from './time';

describe('conversation time', () => {
  it('normalizes seconds, milliseconds, microseconds and ISO strings', () => {
    expect(normalizeTimestamp(1_720_000_000)).toBe(1_720_000_000_000);
    expect(normalizeTimestamp('1720000000000')).toBe(1_720_000_000_000);
    expect(normalizeTimestamp(1_720_000_000_000_000)).toBe(1_720_000_000_000);
    expect(normalizeTimestamp('2026-07-16T08:30:00.000Z')).toBe(Date.parse('2026-07-16T08:30:00.000Z'));
  });

  it('uses clear relative Chinese labels', () => {
    const now = new Date(2026, 6, 16, 18, 0).getTime();
    expect(formatConversationTime(new Date(2026, 6, 16, 9, 5).getTime(), now)).toContain('今天');
    expect(formatConversationTime(new Date(2026, 6, 15, 21, 0).getTime(), now)).toContain('昨天');
    expect(formatConversationTime(new Date(2026, 5, 2).getTime(), now)).toBe('6月2日');
    expect(formatConversationTime(new Date(2025, 5, 2).getTime(), now)).toBe('2025年6月2日');
  });
});
