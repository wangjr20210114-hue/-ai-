import type { ProactiveNotification } from '../../types';
import { translate } from '../../i18n';

export interface ProactiveReminderLine {
  id: string;
  notificationId: string;
  text: string;
}

function defaultProactiveFallbacks(): string[] {
  return [
  translate('defaultMotto1'),
  translate('defaultMotto2'),
  translate('defaultMotto3'),
  translate('defaultMotto4'),
  translate('defaultMotto5'),
  translate('defaultMotto6'),
  translate('defaultMotto7'),
  translate('defaultMotto8'),
  translate('defaultMotto9'),
  translate('defaultMotto10'),
  ];
}

/** Build presentation-only fallbacks without creating fake notifications. */
export function proactiveFallbackLines(items: string[]): ProactiveReminderLine[] {
  const seen = new Set<string>();
  return [...items, ...defaultProactiveFallbacks()].flatMap((item, index) => {
    const text = String(item || '').replace(/\s+/g, ' ').trim().slice(0, 80);
    if (!text || seen.has(text)) return [];
    seen.add(text);
    return [{
      id: `fallback:${index}:${text}`,
      notificationId: '',
      text,
    }];
  }).slice(0, 10);
}

export function activeProactiveNotifications(
  items: ProactiveNotification[],
  now = Math.floor(Date.now() / 1000),
): ProactiveNotification[] {
  return items
    .filter((item) => item.status === 'unread' || (item.status === 'snoozed' && Number(item.snoozed_until || 0) > now))
    .slice(0, 10);
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function finishSentence(text: string): string {
  const clean = text
    .replace(/\s+/g, ' ')
    .replace(/[。！？；，、,.!?;]+$/u, '')
    .trim();
  return clean ? `${clean}${translate('sentencePeriod')}` : '';
}

function weatherSentence(item: ProactiveNotification): string {
  const evidence = record(item.evidence);
  const weather = record(evidence.weather);
  const schedule = record(evidence.schedule);
  const condition = String(weather.weather || '').trim();
  if (!condition) return '';
  const location = String(
    weather.district
    || weather.city
    || schedule.location
    || translate('yourArea'),
  ).trim();
  let advice = translate('weatherPrepare');
  if (/[雷雨]/u.test(condition)) advice = translate('weatherRainAdvice');
  else if (/[雪冻冰雹]/u.test(condition)) advice = translate('weatherSnowAdvice');
  else if (/[风台风沙尘]/u.test(condition)) advice = translate('weatherWindAdvice');
  else if (/雾/u.test(condition)) advice = translate('weatherFogAdvice');
  return finishSentence(translate('weatherReminder', { location, condition, advice }));
}

function compactReminder(text: string, maxLength = 80): string {
  const natural = finishSentence(text);
  if (natural.length <= maxLength) return natural;
  const punctuation = translate('sentencePeriod');
  return `${natural.slice(0, Math.max(1, maxLength - punctuation.length - 1)).trim()}…${punctuation}`;
}

/** Convert every structured event into exactly one compact Header line. */
export function proactiveReminderLines(items: ProactiveNotification[]): ProactiveReminderLine[] {
  return items.flatMap((item) => {
    const natural = item.type === 'weather_risk'
      ? weatherSentence(item)
      : finishSentence(item.body || item.title);
    const text = compactReminder(natural);
    return text ? [{
      id: item.id,
      notificationId: item.id,
      text,
    }] : [];
  });
}

/** Fill the ten-slot Header window without turning fallback prose into events. */
export function proactiveHeaderLines(
  reminders: ProactiveReminderLine[],
  fallbacks: ProactiveReminderLine[],
  limit = 10,
): ProactiveReminderLine[] {
  const output = reminders.slice(0, limit);
  const used = new Set(output.map((item) => item.text));
  for (const fallback of fallbacks) {
    if (output.length >= limit) break;
    if (!fallback.text || used.has(fallback.text)) continue;
    used.add(fallback.text);
    output.push(fallback);
  }
  return output;
}
