import type { ProactiveNotification } from '../../types';

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
