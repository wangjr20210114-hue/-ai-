import type { RichMediaAsset, SearchResultItem } from '../../types';

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
  // Strip citation markers — we don't want numbered superscript links in the answer.
  // Sources are still available in the search_results panel below the message.
  let result = content.replace(/\[\[cite:(source-[a-zA-Z0-9_-]+)\]\]/g, '');
  // Also strip any leaked [[xxx] yyy] patterns from search providers (e.g. [[wsa] title])
  result = result.replace(/\[\[[^\]]*\][^\]]*\]/g, '');
  return result.trim();
}

export function expandStructuredCards(content: string, sources: SearchResultItem[]): string {
  const byId = new Map(sources.map(source => [source.id, source]));
  return content.replace(/\[\[card:(source-[a-zA-Z0-9_-]+)\]\]/g, (_match, sourceId: string) => {
    const source = byId.get(sourceId);
    if (!source || !isSafeRemoteUrl(source.url)) return '';
    const labels: Record<string, string> = {
      wechat: '公众号', zhihu: '知乎', baike: '百科', web: '网页', wsa: '联网',
    };
    const clean = (value: string) => value
      .split('|').join(' ')
      .split('[').join(' ')
      .split(']').join(' ')
      .replace(/\n/g, ' ')
      .trim();
    return `[[card:${labels[source.source] || '网页'}|${clean(source.title)}|${source.url}|${clean(source.snippet)}]]`;
  });
}

export function resolveMediaReference(
  reference: string,
  media: RichMediaAsset[],
): RichMediaAsset | undefined {
  const structured = media.find(item => item.id === reference);
  if (structured && isSafeRemoteUrl(structured.url)) return structured;
  if (isSafeRemoteUrl(reference)) {
    return {
      id: `legacy-${reference}`,
      kind: 'image',
      url: reference,
      alt: '',
      caption: '',
      generated: false,
    };
  }
  return undefined;
}
