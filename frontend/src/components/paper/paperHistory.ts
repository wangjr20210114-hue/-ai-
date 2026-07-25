import type { PaperAssistantResult } from '../../services/paperApi';

export function newestTranslationsFirst(
  items: PaperAssistantResult[],
): PaperAssistantResult[] {
  return items
    .filter((item) => item.action === 'translate')
    .sort((left, right) => (
      Number(right.created_at || 0) - Number(left.created_at || 0)
      || right.id.localeCompare(left.id)
    ))
    .slice(0, 50);
}
