import { describe, expect, it } from 'vitest';
import { isAllowedSearchUrl, replaceCitationMarkers } from './richContent';
import type { SearchMeta, SearchResultItem } from '../../types';

const source: SearchResultItem = {
  id: 'source-1',
  source: 'web',
  title: '官方说明',
  snippet: '可信摘要',
  url: 'https://example.com/source',
};

describe('rich content references', () => {
  it('strips citation markers from content', () => {
    const result = replaceCitationMarkers('结论。[[cite:source-1]] [[cite:source-9]]', [source]);
    expect(result).toBe('结论。');
  });

  it('only allows source-bound images in a search answer', () => {
    const meta: SearchMeta = {
      query: '北京去哪玩', results: [source], images: ['https://example.com/view.jpg'],
      media: [{
        id: 'media-1', kind: 'image', url: 'https://example.com/view.jpg',
        alt: '北京景点', caption: '北京景点', generated: false,
      }],
      sources_used: ['web'], total: 1,
    };
    expect(isAllowedSearchUrl('https://example.com/view.jpg', meta, 'image')).toBe(true);
    expect(isAllowedSearchUrl('https://untrusted.example/image.jpg', meta, 'image')).toBe(false);
    expect(isAllowedSearchUrl(source.url, meta)).toBe(true);
  });
});
