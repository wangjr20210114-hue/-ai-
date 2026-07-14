import type { SearchMeta, SearchResultItem } from '../../types';
import { isSafeHttpUrl } from '../../services/search';

export function isSafeRemoteUrl(value: string): boolean {
  return isSafeHttpUrl(value);
}

export function isAllowedSearchUrl(value: string, searchMeta?: SearchMeta, kind?: 'image'): boolean {
  if (!isSafeRemoteUrl(value)) return false;
  if (!searchMeta) return true;
  if (kind === 'image') {
    return searchMeta.media.some(item => item.kind !== 'video' && item.url === value);
  }
  return searchMeta.results.some(item => item.url === value)
    || searchMeta.media.some(item => item.url === value || item.source_url === value);
}

export function replaceCitationMarkers(content: string, _sources: SearchResultItem[]): string {
  void _sources;
  // Strip citation markers — we don't want numbered superscript links in the answer.
  // Sources are still available in the search_results panel below the message.
  let result = content.replace(/\[\[cite:(source-[a-zA-Z0-9_-]+)\]\]/g, '');
  // Also strip any leaked [[xxx] yyy] patterns from search providers (e.g. [[wsa] title])
  result = result.replace(/\[\[[^\]]*\][^\]]*\]/g, '');
  return result.trim();
}


