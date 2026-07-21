import { describe, expect, it } from 'vitest';
import { mergeSearchMeta } from './useSSEChat';
import type { SearchMeta } from '../types';

const media = [{
  id: 'media-1', kind: 'image' as const, url: 'https://example.com/news.jpg',
  alt: '新闻现场', caption: '新闻现场', generated: false,
}];

describe('mergeSearchMeta', () => {
  it('retains progressive media when it arrives before base search results', () => {
    const mediaFirst = mergeSearchMeta(undefined, {
      query: 'AI 新闻', media, images: [media[0].url], media_pending: false,
    });
    const merged = mergeSearchMeta(mediaFirst, {
      query: 'AI 新闻', results: [], media: [], images: [], sources_used: ['wsa'], total: 0, media_pending: true,
    });
    expect(merged.media).toEqual(media);
    expect(merged.images).toEqual([media[0].url]);
    expect(merged.media_pending).toBe(false);
  });

  it('adds progressive media when base search results arrive first', () => {
    const base: SearchMeta = {
      query: 'AI 新闻', results: [], media: [], images: [], sources_used: ['wsa'], total: 0, media_pending: true,
    };
    const merged = mergeSearchMeta(base, {
      media, images: [media[0].url], media_pending: false,
    });
    expect(merged.media).toEqual(media);
    expect(merged.media_pending).toBe(false);
  });
});
