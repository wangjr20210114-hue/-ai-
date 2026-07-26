import { describe, expect, it } from 'vitest';
import { publicAssistantMarkdown } from './streamingAnswer';

describe('publicAssistantMarkdown', () => {
  it('removes leaked internal action buttons while preserving the answer', () => {
    expect(publicAssistantMarkdown(
      '附近有不少公园。\n\n<button data-action="map" data-action-id="maprec_123">在地图中查看</button>',
    )).toBe('附近有不少公园。');
  });

  it('preserves ordinary HTML examples without internal action attributes', () => {
    const example = '可以这样写：\n\n<button type="button">保存</button>';
    expect(publicAssistantMarkdown(example)).toBe(example);
  });

  it('hides an unfinished internal action button during streaming', () => {
    expect(publicAssistantMarkdown(
      '地点已找到。\n\n<button data-action="map" data-action-id="maprec_123"',
    )).toBe('地点已找到。');
  });
});
