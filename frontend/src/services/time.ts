export function normalizeTimestamp(value: unknown, fallback = Date.now()): number {
  if (value instanceof Date) {
    const timestamp = value.getTime();
    return Number.isFinite(timestamp) ? timestamp : fallback;
  }
  const text = typeof value === 'string' ? value.trim() : '';
  const numeric = typeof value === 'number'
    ? value
    : text && /^-?\d+(?:\.\d+)?$/.test(text) ? Number(text) : Number.NaN;
  if (Number.isFinite(numeric) && numeric > 0) {
    if (numeric < 100_000_000_000) return Math.round(numeric * 1000);
    if (numeric > 10_000_000_000_000) return Math.round(numeric / 1000);
    return Math.round(numeric);
  }
  if (text) {
    const parsed = Date.parse(text);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

export function formatConversationTime(value: unknown, nowValue = Date.now()): string {
  const timestamp = normalizeTimestamp(value, Number.NaN);
  if (!Number.isFinite(timestamp)) return '';
  const date = new Date(timestamp);
  const now = new Date(nowValue);
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const dayStart = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const time = date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
  if (dayStart === startOfToday) return `今天 ${time}`;
  if (dayStart === startOfToday - 86_400_000) return `昨天 ${time}`;
  if (date.getFullYear() === now.getFullYear()) return `${date.getMonth() + 1}月${date.getDate()}日`;
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`;
}
