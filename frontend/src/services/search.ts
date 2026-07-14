import type { RichMediaAsset, SearchMeta, SearchResultItem } from '../types';

export function isSafeHttpUrl(value: string): boolean {
  try {
    const url = new URL(value);
    if ((url.protocol !== 'https:' && url.protocol !== 'http:') || url.username || url.password) return false;
    const host = url.hostname.toLowerCase().replace(/\.$/, '');
    if (host === 'localhost' || host.endsWith('.localhost') || host.endsWith('.local') || host.endsWith('.internal')) return false;
    if (/^(127\.|0\.|10\.|192\.168\.|169\.254\.)/.test(host)) return false;
    const match = host.match(/^172\.(\d{1,3})\./);
    if (match && Number(match[1]) >= 16 && Number(match[1]) <= 31) return false;
    if (host === '::1' || host.startsWith('fc') || host.startsWith('fd') || host.startsWith('fe80:')) return false;
    return true;
  } catch {
    return false;
  }
}

function record(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined;
}

export function normalizeSearchMeta(value: unknown): SearchMeta | undefined {
  const raw = record(value);
  if (!raw || !Array.isArray(raw.results)) return undefined;

  const results: SearchResultItem[] = raw.results.flatMap((entry, index) => {
    const item = record(entry);
    const url = typeof item?.url === 'string' ? item.url : '';
    if (!item || !isSafeHttpUrl(url)) return [];
    return [{
      id: String(item.id || `source-${index + 1}`),
      source: String(item.source || 'web'),
      title: String(item.title || url),
      snippet: String(item.snippet || ''),
      url,
      ...(typeof item.account_name === 'string' ? { account_name: item.account_name } : {}),
    }];
  });

  const media: RichMediaAsset[] = (Array.isArray(raw.media) ? raw.media : []).flatMap((entry, index) => {
    const item = record(entry);
    const url = typeof item?.url === 'string' ? item.url : '';
    if (!item || !isSafeHttpUrl(url)) return [];
    const sourceUrl = typeof item.source_url === 'string' && isSafeHttpUrl(item.source_url)
      ? item.source_url
      : undefined;
    return [{
      id: String(item.id || `media-${index + 1}`),
      kind: item.kind === 'video' ? 'video' : 'image',
      url,
      source_id: typeof item.source_id === 'string' ? item.source_id : undefined,
      source_url: sourceUrl,
      source_title: String(item.source_title || ''),
      alt: String(item.alt || item.caption || '相关媒体'),
      caption: String(item.caption || item.alt || '相关媒体'),
      attribution: typeof item.attribution === 'string' ? item.attribution : undefined,
      generated: item.generated === true,
    }];
  });

  if (!results.length) return undefined;
  return {
    schema_version: Number(raw.schema_version || 2),
    query: String(raw.query || ''),
    results,
    images: media.filter(item => item.kind === 'image').map(item => item.url),
    media,
    sources_used: Array.from(new Set(results.map(item => item.source))),
    total: results.length,
  };
}
