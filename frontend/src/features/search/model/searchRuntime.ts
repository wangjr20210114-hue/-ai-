import type { SearchMeta } from './types';

export function resolveSearchStartAt(
  current: number | undefined,
  remembered: number | undefined,
  shouldStart: boolean,
  now = Date.now(),
): number | undefined {
  const known = Number(remembered || current || 0);
  return known || (shouldStart ? now : undefined);
}

export function mergeSearchMeta(
  previous: SearchMeta | undefined,
  incoming: Partial<SearchMeta>,
): SearchMeta {
  const previousMedia = previous?.media || [];
  const incomingMedia = Array.isArray(incoming.media) ? incoming.media : [];
  const previousImages = previous?.images || [];
  const incomingImages = Array.isArray(incoming.images) ? incoming.images : [];
  return {
    ...(previous || {}),
    ...incoming,
    query: String(incoming.query ?? previous?.query ?? ''),
    results: Array.isArray(incoming.results) ? incoming.results : (previous?.results || []),
    media: incomingMedia.length ? incomingMedia : previousMedia,
    images: incomingImages.length ? incomingImages : previousImages,
    sources_used: Array.isArray(incoming.sources_used)
      ? incoming.sources_used
      : (previous?.sources_used || []),
    total: typeof incoming.total === 'number' ? incoming.total : (previous?.total || 0),
    timings_ms: incoming.timings_ms ?? previous?.timings_ms,
    media_pending: previous?.media_pending === false && previousMedia.length > 0
      ? false
      : (incoming.media_pending ?? previous?.media_pending),
  };
}
