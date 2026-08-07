import type { SearchResultItem } from '../../features/search/model';
import { translate } from '../../i18n';

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

function cleanLabel(value: string): string {
  return value.trim().replace(/[\r\n]+/g, ' ').replace(/\s{2,}/g, ' ');
}

/** Count evidence actually cited by the answer, not merely fetched candidates. */
export function citedSearchSourceCount(
  content: string,
  sources: SearchResultItem[] = [],
): number {
  const citedUrls = new Set(
    [...String(content || '').matchAll(/https?:\/\/[^\s)\]]+/g)]
      .map((match) => normalizedUrl(match[0])),
  );
  return sources.filter((source, index) => (
    isSafeRemoteUrl(source.url)
    && citedUrls.has(normalizedUrl(source.url))
    && sources.findIndex((candidate) => normalizedUrl(candidate.url) === normalizedUrl(source.url)) === index
  )).length;
}

export function sourceLabel(url: string, sources: SearchResultItem[] = []): string {
  const source = sourceForUrl(url, sources);
  if (source?.title?.trim()) return cleanLabel(source.title).split('[').join(' ').split(']').join(' ');
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return translate('viewSource');
  }
}

/** Prefer the publisher carried by the search contract over a relay hostname. */
export function sourcePublisherLabel(url: string, sources: SearchResultItem[] = []): string {
  const source = sourceForUrl(url, sources);
  const publisher = cleanLabel(source?.publisher || '');
  if (publisher) return publisher;
  const publisherDomain = cleanLabel(source?.publisher_domain || '');
  if (publisherDomain) return publisherDomain.replace(/^www\./, '');
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return translate('viewSource');
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
    // Keep the URL as the temporary Markdown label. MarkdownRenderer recognizes
    // URL-only citations and supplies the current interface-language label.
    return `([${url}](${url}))`;
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

export function replaceCitationMarkers(content: string, sources: SearchResultItem[]): string {
  // Models may return the stable source id marker even when they omit the
  // Markdown link requested by the public answer contract. Resolve known
  // markers into the same compact link used for ordinary citations; unknown
  // markers remain hidden instead of exposing an internal id.
  let result = content.replace(/\[\[cite:(source-[a-zA-Z0-9_-]+)\]\]/g, (_match, sourceId: string) => {
    const source = sources.find((item) => item.id === sourceId && isSafeRemoteUrl(item.url));
    return source ? `[${source.title || sourceLabel(source.url, sources)}](${source.url})` : '';
  });
  // Also strip any leaked [[xxx] yyy] patterns from search providers (e.g. [[wsa] title])
  result = result.replace(/\[\[[^\]]*\][^\]]*\]/g, '');
  return result.trim();
}
