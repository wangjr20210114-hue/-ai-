import type { PaperInfo } from '../types';

export function dedupePapers(items: PaperInfo[]): PaperInfo[] {
  const seenIds = new Set<string>();
  const seenTitles = new Set<string>();
  return items.filter((paper) => {
    const id = String(paper.arxiv_id || '').toLowerCase().replace(/v\d+$/, '');
    const title = paper.title.toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]+/g, '');
    if ((id && seenIds.has(id)) || (title && seenTitles.has(title))) return false;
    if (id) seenIds.add(id);
    if (title) seenTitles.add(title);
    return true;
  });
}

export function paperArxivHref(paper: PaperInfo): string {
  if (paper.arxiv_url) return paper.arxiv_url;
  if (paper.arxiv_id && !/^web(?:pdf|paper)-/i.test(paper.arxiv_id)) {
    return `https://arxiv.org/abs/${encodeURIComponent(paper.arxiv_id)}`;
  }
  return '';
}

export function paperSourceHref(paper: PaperInfo): string {
  return paperArxivHref(paper) || paper.source_url || '';
}

function stablePaperHash(value: string): string {
  let hash = 2166136261;
  for (const character of value) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16);
}

/**
 * Source-only papers are resolved lazily through DOI/OpenAlex metadata or an
 * exact-title arXiv lookup. A stable id also keeps repeated downloads
 * de-duplicated in the user's reading library.
 */
export function paperDownloadId(paper: PaperInfo): string {
  if (paper.arxiv_id) return paper.arxiv_id;
  const identity = paper.pdf_url || paper.source_url || paper.title;
  return identity ? `webpaper-${stablePaperHash(identity)}` : '';
}
