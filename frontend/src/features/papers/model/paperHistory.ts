import type { PaperAssistantResult } from './types';

/** Keep the reader timeline append-only: older translations remain above the latest one. */
export function translationsInTimeOrder(items: PaperAssistantResult[]): PaperAssistantResult[] {
  return items
    .filter((item) => item.action === 'translate')
    .sort(
      (left, right) => Number(left.created_at || 0) - Number(right.created_at || 0)
        || left.id.localeCompare(right.id),
    )
    .slice(-50);
}
