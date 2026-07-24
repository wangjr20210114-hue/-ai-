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
  const language = getStoredLanguage();
  const locale = language === 'zh-TW' ? 'zh-TW' : language === 'en' ? 'en' : 'zh-CN';
  const time = date.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit', hour12: false });
  if (dayStart === startOfToday) return translate('todayAt', { time }, language);
  if (dayStart === startOfToday - 86_400_000) return translate('yesterdayAt', { time }, language);
  return date.toLocaleDateString(locale, date.getFullYear() === now.getFullYear()
    ? { month: 'long', day: 'numeric' }
    : { year: 'numeric', month: 'long', day: 'numeric' });
}
import { getStoredLanguage, translate } from '../i18n';
