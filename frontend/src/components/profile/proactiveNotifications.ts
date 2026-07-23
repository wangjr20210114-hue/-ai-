import type { ProactiveNotification } from '../../types';

export interface ProactiveReminderLine {
  id: string;
  notificationId: string;
  text: string;
}

export function activeProactiveNotifications(
  items: ProactiveNotification[],
  now = Math.floor(Date.now() / 1000),
): ProactiveNotification[] {
  return items
    .filter((item) => item.status === 'unread' || (item.status === 'snoozed' && Number(item.snoozed_until || 0) > now))
    .sort((left, right) => {
      const rank = { high: 0, normal: 1, low: 2 };
      return rank[left.priority] - rank[right.priority] || right.updated_at - left.updated_at;
    })
    .slice(0, 4);
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
  return clean ? `${clean}。` : '';
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
    || '你所在地区',
  ).trim();
  let advice = '出门前记得做好准备';
  if (/[雷雨]/u.test(condition)) advice = '记得带伞，也注意保暖';
  else if (/[雪冻冰雹]/u.test(condition)) advice = '记得保暖并注意路滑';
  else if (/[风台风沙尘]/u.test(condition)) advice = '记得防风，出行注意安全';
  else if (/雾/u.test(condition)) advice = '能见度可能较低，出行注意安全';
  return finishSentence(`今天${location}有${condition}，${advice}`);
}

function splitReminder(text: string, maxLength = 36): string[] {
  const sentences = text.match(/[^。！？；]+[。！？；]?/gu) || [text];
  const output: string[] = [];
  sentences.forEach((sentence) => {
    const clean = sentence.trim();
    if (!clean) return;
    if (clean.length <= maxLength) {
      output.push(finishSentence(clean));
      return;
    }
    const clauses = clean.split(/[，,]/u).map((part) => part.trim()).filter(Boolean);
    let current = '';
    clauses.forEach((clause) => {
      const next = current ? `${current}，${clause}` : clause;
      if (current && next.length > maxLength) {
        output.push(finishSentence(current));
        current = clause;
      } else {
        current = next;
      }
    });
    if (current) output.push(finishSentence(current));
  });
  return output.filter(Boolean);
}

/** Convert structured notifications into short, conversational Header lines. */
export function proactiveReminderLines(items: ProactiveNotification[]): ProactiveReminderLine[] {
  return items.flatMap((item) => {
    const natural = item.type === 'weather_risk'
      ? weatherSentence(item)
      : finishSentence(item.body || item.title);
    return splitReminder(natural).map((text, index) => ({
      id: `${item.id}:${index}`,
      notificationId: item.id,
      text,
    }));
  });
}
