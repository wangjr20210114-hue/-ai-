import { describe, expect, it } from 'vitest';
import { isSafeHttpUrl, normalizeSearchMeta } from './search';

describe('rich search transport', () => {
  it('rejects local and credential-bearing URLs', () => {
    expect(isSafeHttpUrl('http://127.0.0.1/private')).toBe(false);
    expect(isSafeHttpUrl('https://user:pass@example.com/image.jpg')).toBe(false);
    expect(isSafeHttpUrl('https://example.com/image.jpg')).toBe(true);
  });

  it('normalizes structured sources and media', () => {
    const meta = normalizeSearchMeta({
      query: '北京去哪玩',
      results: [{ id: 'source-1', source: 'wechat', title: '北京文旅', snippet: '景点', url: 'https://example.com/article' }],
      media: [
        { id: 'media-1', kind: 'image', url: 'https://cdn.example.com/view.jpg', caption: '北京景点' },
        { id: 'media-2', kind: 'image', url: 'http://localhost/secret.jpg' },
      ],
    });
    expect(meta?.total).toBe(1);
    expect(meta?.media.map(item => item.id)).toEqual(['media-1']);
    expect(meta?.images).toEqual(['https://cdn.example.com/view.jpg']);
  });
});
