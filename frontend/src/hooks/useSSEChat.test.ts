import { describe, expect, it } from 'vitest';
import { actionOnlyFallback, mergeSearchMeta, progressTextForTool, shouldPublishProactiveOpening } from './useSSEChat';
import type { WorkspaceAction } from '../types';
import type { ChatMessage, SearchMeta } from '../types';

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

describe('shouldPublishProactiveOpening', () => {
  it('allows an opening only while the conversation is still empty', () => {
    expect(shouldPublishProactiveOpening([], [])).toBe(true);
  });

  it('never replaces a user message sent while the opening was composed', () => {
    const latest: ChatMessage[] = [{
      id: 'user-race', role: 'user', content: '我先问一个问题', ts: Date.now(),
    }];
    expect(shouldPublishProactiveOpening([], latest)).toBe(false);
  });
});

describe('actionOnlyFallback', () => {
  it('keeps a successful map Action visible when final model prose is empty', () => {
    const action = {
      id: 'map-1', kind: 'map_recommendation', status: 'ready', version: 1, payload: {},
    } as WorkspaceAction;
    expect(actionOnlyFallback([action])).toContain('点击');
  });
});

describe('human-readable progress', () => {
  it('explains search progress without exposing Agent implementation jargon', () => {
    expect(progressTextForTool('rich_search', 'active')).toContain('可靠');
    expect(progressTextForTool('rich_search', 'complete')).toContain('核对');
    expect(progressTextForTool('rich_search', 'complete')).not.toContain('工具');
  });

  it('uses a plain-language fallback for an unfamiliar capability', () => {
    expect(progressTextForTool('future_capability', 'complete')).toBe('这一步已完成，正在整理结果…');
  });
});
