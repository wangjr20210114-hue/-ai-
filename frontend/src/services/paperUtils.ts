import type { PaperInfo } from '../types';

export function dedupePapers(items: PaperInfo[]): PaperInfo[] {
  const seenIds = new Set<string>();
  const seenTitles = new Set<string>();
  return items.filter((paper) => {
    const id = paper.arxiv_id.toLowerCase().replace(/v\d+$/, '');
    const title = paper.title.toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]+/g, '');
    if ((id && seenIds.has(id)) || (title && seenTitles.has(title))) return false;
    if (id) seenIds.add(id);
    if (title) seenTitles.add(title);
    return true;
  });
}
