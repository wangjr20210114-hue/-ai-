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

function normalizedUrl(value: string): string {
  try {
    const url = new URL(value);
    url.hash = '';
    return url.toString().replace(/\/$/, '');
  } catch {
    return value.trim().replace(/\/$/, '');
  }
}

function sourceForUrl(url: string, sources: SearchResultItem[]): SearchResultItem | undefined {
  const normalized = normalizedUrl(url);
  return sources.find((source) => normalizedUrl(source.url) === normalized);
}

export function sourceLabel(url: string, sources: SearchResultItem[] = []): string {
  const source = sourceForUrl(url, sources);
  if (source?.title?.trim()) return source.title.trim().split(/[\r\n]/).join(' ').split('[').join(' ').split(']').join(' ');
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return '查看来源';
  }
}

/**
 * Some providers leak a bare URL wrapped in parentheses instead of emitting a
 * Markdown link. Turn only known search-result URLs into proper links so the
 * evidence remains clickable without making arbitrary prose URLs interactive.
 */
export function linkBareCitations(content: string, sources: SearchResultItem[] = []): string {
  if (!sources.length) return content;
  return content.replace(/(?<!\])\((https?:\/\/[^\s)]+)\)/g, (match, url: string) => {
    if (!sourceForUrl(url, sources)) return match;
    return `([${sourceLabel(url, sources)}](${url}))`;
  });
}

/** Convert the answer Markdown into text-only clipboard content. */
export function markdownToPlainText(content: string, sources: SearchResultItem[] = []): string {
  const text = content
    .replace(/\[\[YUANBAO_MEDIA[^\]]*\]\]/g, '')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, (_match, label: string, url: string) => (
      sourceForUrl(url, sources) ? '' : label
    ))
    .replace(/(?<!\])\((https?:\/\/[^\s)]+)\)/g, (_match, url: string) => (
      sourceForUrl(url, sources) ? '' : url
    ))
    .replace(/https?:\/\/[^\s)]+/g, (url: string) => (sourceForUrl(url, sources) ? '' : url))
    .replace(/^\s{0,3}#{1,6}\s+/gm, '')
    .replace(/^\s{0,3}(?:[-*+] |\d+[.)] )/gm, '')
    .replace(/```(?:[\w-]+)?\n?/g, '')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/[*_~]/g, '');
  return text
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

export function replaceCitationMarkers(content: string, _sources: SearchResultItem[]): string {
  void _sources;
  // Strip internal citation markers; user-facing links are rendered inline below.
  let result = content.replace(/\[\[cite:(source-[a-zA-Z0-9_-]+)\]\]/g, '');
  // Also strip any leaked [[xxx] yyy] patterns from search providers (e.g. [[wsa] title])
  result = result.replace(/\[\[[^\]]*\][^\]]*\]/g, '');
  return result.trim();
}
