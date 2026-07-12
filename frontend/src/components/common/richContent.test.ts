import { describe, expect, it } from 'vitest';
import { replaceCitationMarkers, resolveMediaReference } from './richContent';
import type { RichMediaAsset, SearchResultItem } from '../../types';

const source: SearchResultItem = {
  id: 'source-1',
  source: 'web',
  title: '官方说明',
  snippet: '可信摘要',
  url: 'https://example.com/source',
};

const media: RichMediaAsset = {
  id: 'media-1',
  kind: 'image',
  url: 'https://example.com/image.png',
  source_id: 'source-1',
  source_url: source.url,
  source_title: source.title,
  alt: '示例图',
  caption: '示例图片说明',
  attribution: source.title,
  generated: false,
};

describe('rich content references', () => {
  it('resolves only known media IDs and safe legacy URLs', () => {
    expect(resolveMediaReference('media-1', [media])?.caption).toBe('示例图片说明');
    expect(resolveMediaReference('media-404', [media])).toBeUndefined();
    expect(resolveMediaReference('javascript:alert(1)', [media])).toBeUndefined();
  });

  it('strips citation markers from content', () => {
    const result = replaceCitationMarkers('结论。[[cite:source-1]] [[cite:source-9]]', [source]);
    expect(result).toBe('结论。');
  });
});
