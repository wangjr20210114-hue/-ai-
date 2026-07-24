import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ChatMessage } from '../types';
import { canReusePendingConversation, clearLocalApplicationData, coalesceActionMessages, coalesceDuplicateAssistantMessages, createConversationId, durableMessageCount, getOrCreateConversationId, loadLocalConversations, makersConversationHeaders, mergeMessages, reconcileCompletedMessage, reconcileConversationSummary, saveLocalConversations, setActiveConversationId, settleStoppedMessages } from './conversation';
import { CONVERSATION_PREFIX, isCurrentConversationId } from './dataVersion';

describe('getOrCreateConversationId', () => {
  beforeEach(() => {
    const values = new Map<string, string>();
    const sessionValues = new Map<string, string>();
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
      clear: () => values.clear(),
    });
    vi.stubGlobal('sessionStorage', {
      getItem: (key: string) => sessionValues.get(key) ?? null,
      setItem: (key: string, value: string) => sessionValues.set(key, value),
      removeItem: (key: string) => sessionValues.delete(key),
      clear: () => sessionValues.clear(),
    });
    vi.stubGlobal('window', globalThis);
  });

  afterEach(() => vi.unstubAllGlobals());

  it('persists one conversation id for every Makers endpoint', () => {
    const first = getOrCreateConversationId();
    const second = getOrCreateConversationId();
    expect(first).toBe(second);
    expect(first.length).toBeGreaterThan(10);
  });

  it('remembers an explicitly selected Makers conversation', () => {
    setActiveConversationId('conv-local-history');
    expect(getOrCreateConversationId()).toBe('conv-local-history');
  });

  it('creates collision-resistant ids for fresh conversations', () => {
    expect(createConversationId()).not.toBe(createConversationId());
    expect(createConversationId().startsWith(CONVERSATION_PREFIX)).toBe(true);
    expect(createConversationId().length).toBeLessThanOrEqual(36);
    expect(isCurrentConversationId(createConversationId())).toBe(true);
    expect(isCurrentConversationId('legacy-conversation')).toBe(false);
  });

  it('uses the Makers conversation header for every agent endpoint', () => {
    expect(makersConversationHeaders('conversation-123')).toEqual({
      'makers-conversation-id': 'conversation-123',
    });
  });

  it('persists the local conversation index across reloads', () => {
    const items = [{ id: 'conv-1', title: '已存在的对话', createdAt: 1, updatedAt: 2, messageCount: 3 }];
    saveLocalConversations(items);
    expect(loadLocalConversations()).toEqual(items);
  });

  it('keeps a running marker across reload so the page can reconnect', () => {
    saveLocalConversations([{ id: 'conv-running', title: '进行中', createdAt: 1, updatedAt: 2, messageCount: 1, activityStatus: 'running' }]);
    expect(loadLocalConversations()[0].activityStatus).toBe('running');
  });

  it('clears browser-side application state after a server reset', () => {
    localStorage.setItem('floris-language', 'en');
    sessionStorage.setItem('floris.manual-stop.yb7_test', '1');
    clearLocalApplicationData();
    expect(localStorage.getItem('floris-language')).toBeNull();
    expect(sessionStorage.getItem('floris.manual-stop.yb7_test')).toBeNull();
  });
});

describe('mergeMessages', () => {
  it('drops stale local failure prompts before the latest Makers match', () => {
    const local: ChatMessage[] = [
      { id: 'u1', role: 'user', content: '失败一', ts: 1 },
      { id: 'empty-ai', role: 'ai', content: '', ts: 2 },
      { id: 'u2', role: 'user', content: '失败二', ts: 3 },
      { id: 'u3', role: 'user', content: '成功问题', ts: 4 },
      { id: 'a3', role: 'ai', content: '成功回答', ts: 5 },
    ];
    expect(mergeMessages(
      local.slice(-2),
      local,
    ).map((item) => item.id)).toEqual(['u3', 'a3']);
  });

  it('reconciles checkpoint sequence ids with browser timestamps without duplicates or reordering', () => {
    const remote: ChatMessage[] = [
      { id: 'checkpoint-user', role: 'user', content: '今天有什么新闻', ts: 0 },
      { id: 'checkpoint-ai', role: 'ai', content: '这是回答', ts: 1 },
    ];
    const local: ChatMessage[] = [
      { id: 'local-user', role: 'user', content: '今天有什么新闻', ts: 1_784_000_000_000 },
      { id: 'local-ai', role: 'ai', content: '这是回答', ts: 1_784_000_001_000 },
    ];
    const merged = mergeMessages(remote, local);
    expect(merged).toHaveLength(2);
    expect(merged.map((item) => item.id)).toEqual(['checkpoint-user', 'checkpoint-ai']);
    expect(merged.map((item) => item.role)).toEqual(['user', 'ai']);
  });

  it('matches repeated identical turns by occurrence and appends only genuinely local messages', () => {
    const remote: ChatMessage[] = [
      { id: 'r1', role: 'user', content: '再说一次', ts: 0 },
      { id: 'r2', role: 'user', content: '再说一次', ts: 1 },
    ];
    const local: ChatMessage[] = [
      { id: 'l1', role: 'user', content: '再说一次', ts: 10 },
      { id: 'l2', role: 'user', content: '再说一次', ts: 11 },
      { id: 'l3', role: 'ai', content: '尚未同步', ts: 12 },
    ];
    expect(mergeMessages(remote, local).map((item) => item.id)).toEqual(['r1', 'r2', 'l3']);
  });

  it('drops a trailing user-only optimistic suffix after Makers restored history', () => {
    const remote: ChatMessage[] = [
      { id: 'r1', role: 'user', content: '已成功的问题', ts: 0 },
      { id: 'r2', role: 'ai', content: '已成功的回答', ts: 1 },
    ];
    const local: ChatMessage[] = [
      { id: 'l1', role: 'user', content: '已成功的问题', ts: 10 },
      { id: 'l2', role: 'ai', content: '已成功的回答', ts: 11 },
      { id: 'failed-u1', role: 'user', content: '失败后残留一', ts: 12 },
      { id: 'failed-u2', role: 'user', content: '失败后残留二', ts: 13 },
    ];
    expect(mergeMessages(remote, local).map((item) => item.id)).toEqual(['r1', 'r2']);
  });

  it('coalesces restored model prose and action fallback rows by Action ID', () => {
    const action = { id: 'image-duplicate', kind: 'image_generate', status: 'succeeded', version: 1, payload: {} } as never;
    const restored: ChatMessage[] = [
      { id: 'user', role: 'user', content: '画一只猫', ts: 1 },
      { id: 'rich', role: 'ai', content: '图片已经生成，可以继续修改。', ts: 2, workspaceActions: [action] },
      { id: 'fallback', role: 'ai', content: '图片任务已准备好，可在下方图片工坊查看结果。', ts: 3, workspaceActions: [action] },
    ];
    const merged = mergeMessages(restored, []);
    expect(merged).toHaveLength(2);
    expect(merged[1].id).toBe('rich');
    expect(merged[1].content).toBe('图片已经生成，可以继续修改。');
    expect(merged[1].workspaceActions).toEqual([action]);
  });

  it('retains local progressive images when the restored answer has only base search metadata', () => {
    const remote: ChatMessage[] = [{
      id: 'remote-ai', role: 'ai', content: 'AI 新闻回答', ts: 1,
      searchResults: { query: 'AI 新闻', results: [], media: [], images: [], sources_used: ['wsa'], total: 0 },
    }];
    const local: ChatMessage[] = [{
      id: 'local-ai', role: 'ai', content: 'AI 新闻回答', ts: 2,
      searchResults: {
        query: 'AI 新闻', results: [], sources_used: ['wsa'], total: 0,
        media: [{ id: 'hero', kind: 'image', url: 'https://example.com/ai.jpg', alt: 'AI 新闻', caption: 'AI 新闻', generated: false }],
        images: ['https://example.com/ai.jpg'], media_pending: false,
      },
    }];
    const merged = mergeMessages(remote, local);
    expect(merged[0].searchResults?.images).toEqual(['https://example.com/ai.jpg']);
    expect(merged[0].searchResults?.media_pending).toBe(false);
  });

  it('preserves the live stream and progressive image metadata while switching back to a running conversation', () => {
    const remote: ChatMessage[] = [{
      id: 'checkpoint-user', role: 'user', content: '最近 AI 有什么进展', ts: 1,
    }];
    const local: ChatMessage[] = [
      { id: 'local-user', role: 'user', content: '最近 AI 有什么进展', ts: 10 },
      {
        id: 'live-ai', role: 'ai', content: '第一条进展正在输出', ts: 11, streaming: true,
        searchResults: {
          query: 'AI 进展', results: [], sources_used: ['wsa'], total: 0,
          media: [{ id: 'hero', kind: 'image', url: 'https://example.com/live.jpg', alt: 'AI 新闻', caption: 'AI 新闻', generated: false }],
          images: ['https://example.com/live.jpg'], media_pending: false,
        },
      },
    ];
    const merged = mergeMessages(remote, local, { preserveStreaming: true });
    expect(merged).toHaveLength(2);
    expect(merged[1]).toMatchObject({ id: 'live-ai', streaming: true, content: '第一条进展正在输出' });
    expect(merged[1].searchResults?.images).toEqual(['https://example.com/live.jpg']);
  });

  it('preserves an empty thinking placeholder while the remote run is active', () => {
    const remote: ChatMessage[] = [{ id: 'checkpoint-user', role: 'user', content: '问题', ts: 1 }];
    const local: ChatMessage[] = [
      { id: 'local-user', role: 'user', content: '问题', ts: 10 },
      { id: 'live-ai', role: 'ai', content: '', ts: 11, streaming: true },
    ];
    expect(mergeMessages(remote, local, { preserveStreaming: true }).map((item) => item.id))
      .toEqual(['checkpoint-user', 'live-ai']);
  });
});

describe('coalesceDuplicateAssistantMessages', () => {
  it('collapses identical checkpoint and SSE answers in the same user turn', () => {
    const messages: ChatMessage[] = [
      { id: 'user', role: 'user', content: '最近 AI 有什么进展', ts: 1 },
      { id: 'checkpoint-ai', role: 'ai', content: '这里是最新进展。', ts: 2 },
      {
        id: 'live-ai', role: 'ai', content: '这里是最新进展。', ts: 3,
        searchResults: {
          query: 'AI 进展', results: [], sources_used: ['wsa'], total: 0,
          media: [], images: ['https://example.com/news.jpg'], media_pending: false,
        },
      },
    ];
    const coalesced = coalesceDuplicateAssistantMessages(messages);
    expect(coalesced).toHaveLength(2);
    expect(coalesced[1].id).toBe('checkpoint-ai');
    expect(coalesced[1].searchResults?.images).toEqual(['https://example.com/news.jpg']);
  });

  it('preserves the same answer when it belongs to two separate user turns', () => {
    const messages: ChatMessage[] = [
      { id: 'u1', role: 'user', content: '再说一次', ts: 1 },
      { id: 'a1', role: 'ai', content: '相同回答', ts: 2 },
      { id: 'u2', role: 'user', content: '再说一次', ts: 3 },
      { id: 'a2', role: 'ai', content: '相同回答', ts: 4 },
    ];
    expect(coalesceDuplicateAssistantMessages(messages)).toEqual(messages);
  });

  it('keeps identical prose for unrelated Workspace Actions', () => {
    const first = { id: 'map-a', kind: 'map_recommendation', status: 'ready', version: 1, payload: {} } as never;
    const second = { id: 'map-b', kind: 'map_recommendation', status: 'ready', version: 1, payload: {} } as never;
    const messages: ChatMessage[] = [
      { id: 'user', role: 'user', content: '分别显示两个地点', ts: 1 },
      { id: 'a', role: 'ai', content: '地点已核实。', ts: 2, workspaceActions: [first] },
      { id: 'b', role: 'ai', content: '地点已核实。', ts: 3, workspaceActions: [second] },
    ];
    expect(coalesceDuplicateAssistantMessages(messages)).toHaveLength(3);
  });
});

describe('coalesceActionMessages', () => {
  it('keeps unrelated action rows separate', () => {
    const first = { id: 'map-a', kind: 'map_recommendation', status: 'ready', version: 1, payload: {} } as never;
    const second = { id: 'map-b', kind: 'map_recommendation', status: 'ready', version: 1, payload: {} } as never;
    const messages: ChatMessage[] = [
      { id: 'a', role: 'ai', content: '地点 A', ts: 1, workspaceActions: [first] },
      { id: 'b', role: 'ai', content: '地点 B', ts: 2, workspaceActions: [second] },
    ];
    expect(coalesceActionMessages(messages)).toHaveLength(2);
  });
});

describe('reconcileCompletedMessage', () => {
  it('keeps richer prose and one copy of a durable Action', () => {
    const action = { id: 'map-1', kind: 'map_recommendation', status: 'ready', version: 1, payload: {} } as never;
    const messages: ChatMessage[] = [{
      id: 'checkpoint-ai', role: 'ai', content: '这是模型生成的完整地点说明。', ts: 1, workspaceActions: [action],
    }, {
      id: 'live-ai', role: 'ai', content: '', ts: 2, streaming: true, workspaceActions: [action],
    }];
    const reconciled = reconcileCompletedMessage(messages, {
      ...messages[1], content: '地点已经核实，请点击下方按钮显示地点。', streaming: false,
    });
    expect(reconciled).toHaveLength(1);
    expect(reconciled[0].content).toBe('这是模型生成的完整地点说明。');
    expect(reconciled[0].workspaceActions).toHaveLength(1);
  });

  it('reattaches an Action when a final checkpoint already replaced the live row', () => {
    const action = { id: 'map-2', kind: 'map_recommendation', status: 'ready', version: 1, payload: {} } as never;
    const messages: ChatMessage[] = [{
      id: 'user-1', role: 'user', content: '故宫在哪里？', ts: 1,
    }, {
      id: 'checkpoint-ai', role: 'ai', content: '故宫博物院已完成真实地点核实。', ts: 2,
    }];
    const reconciled = reconcileCompletedMessage(messages, {
      id: 'live-ai', role: 'ai', content: '地点已经过真实地点服务核实。请点击下方按钮显示地点。',
      ts: 3, streaming: false, workspaceActions: [action],
    });
    expect(reconciled).toHaveLength(2);
    expect(reconciled[1].id).toBe('checkpoint-ai');
    expect(reconciled[1].content).toBe('故宫博物院已完成真实地点核实。');
    expect(reconciled[1].workspaceActions).toEqual([action]);
  });
});

describe('pending conversation reuse', () => {
  const pending = { id: 'current', title: '新对话', createdAt: 1, updatedAt: 1, messageCount: 0, pending: true };

  it('does not reuse the active pending summary after real messages exist locally', () => {
    const messages: ChatMessage[] = [
      { id: 'u1', role: 'user', content: '最近有什么 AI 进展', ts: 1 },
      { id: 'a1', role: 'ai', content: '这是搜索后的回答', ts: 2 },
    ];
    expect(durableMessageCount(messages)).toBe(2);
    expect(canReusePendingConversation(pending, 'current', messages)).toBe(false);
  });

  it('reuses a genuinely empty pending conversation', () => {
    expect(canReusePendingConversation(pending, 'current', [])).toBe(true);
  });
});

describe('stopped stream settlement', () => {
  it('removes an empty thinking placeholder and preserves partial text as completed', () => {
    const messages: ChatMessage[] = [
      { id: 'u1', role: 'user', content: '长回答', ts: 1 },
      { id: 'partial', role: 'ai', content: '已经生成的部分', ts: 2, streaming: true },
      { id: 'empty', role: 'ai', content: '', ts: 3, streaming: true },
    ];
    expect(settleStoppedMessages(messages)).toEqual([
      messages[0],
      { ...messages[1], streaming: false },
    ]);
  });
});

describe('eventually consistent conversation summaries', () => {
  it('keeps a known first-message title and message count until Makers indexing catches up', () => {
    const remote = { id: 'conv', title: '新对话', createdAt: 1, updatedAt: 3, messageCount: 0, pending: true };
    const local = { id: 'conv', title: 'TEST-CORE-07-A：北京故宫', createdAt: 1, updatedAt: 2, messageCount: 2, pending: false, activityStatus: 'idle' as const };
    expect(reconcileConversationSummary(remote, local)).toEqual({
      ...remote,
      title: local.title,
      messageCount: 2,
      pending: false,
      activityStatus: 'idle',
    });
  });
});
