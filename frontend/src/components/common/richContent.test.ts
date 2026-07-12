import { describe, expect, it } from 'vitest';
import { replaceCitationMarkers } from './richContent';
import type { SearchResultItem } from '../../types';

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
});
