import type { SearchResultItem } from '../../types';

export function isSafeRemoteUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return (url.protocol === 'https:' || url.protocol === 'http:')
      && !url.username
      && !url.password;
  } catch {
    return false;
  }
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


