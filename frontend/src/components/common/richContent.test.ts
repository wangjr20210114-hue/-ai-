import { describe, expect, it } from 'vitest';
import { markdownToPlainText, replaceCitationMarkers } from './richContent';
import type { SearchResultItem } from '../../shared/types';

const source: SearchResultItem = {
  id: 'source-1',
  source: 'web',
  title: '官方说明',
  snippet: '可信摘要',
  url: 'https://example.com/source',
};

describe('rich content references', () => {
  it('resolves known citation markers into safe source links', () => {
    const result = replaceCitationMarkers('结论。[[cite:source-1]] [[cite:source-9]]', [source]);
    expect(result).toContain('[官方说明](https://example.com/source)');
    expect(result).not.toContain('source-9');
  });

  it('copies answer prose while excluding source URLs and images', () => {
    const result = markdownToPlainText(
      '## 结论\n\n这是 **重点**。\n\n![配图](https://img.example/image.jpg)\n\n[官方说明](https://example.com/source)',
      [source],
    );
    expect(result).toBe('结论\n\n这是 重点。');
    expect(result).not.toContain('example.com');
    expect(result).not.toContain('image.jpg');
  });

});
