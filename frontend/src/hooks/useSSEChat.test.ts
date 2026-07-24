import { describe, expect, it } from 'vitest';
import {
  actionOnlyFallback,
  mergeSearchMeta,
  progressTextForTool,
  shouldPublishProactiveOpening,
  terminalGenerationError,
} from './useSSEChat';
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

  it('describes verified route calculation in user language', () => {
    expect(progressTextForTool('plan_route_between_places', 'active')).toContain('真实道路路线');
    expect(progressTextForTool('plan_route_between_places', 'complete')).toContain('预计时间');
  });
});

describe('terminal generation failure', () => {
  it('turns network failure into a terminal error instead of an automatic retry', () => {
    expect(terminalGenerationError(new TypeError('Failed to fetch'))).toBe('Failed to fetch');
  });

  it('marks watchdog timeout as stopped and explicitly requires a click', () => {
    expect(terminalGenerationError(new DOMException('Aborted', 'AbortError'), true))
      .toContain('不会自动重新生成');
    expect(terminalGenerationError(new DOMException('Aborted', 'AbortError'), true))
      .toContain('点击重试');
  });

  it('treats an explicit abort as a terminal stop', () => {
    expect(terminalGenerationError(new DOMException('Aborted', 'AbortError')))
      .toBe('生成已停止，不会自动重新生成。');
  });
});
