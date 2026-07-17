import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ChatMessage } from '../types';
import { createConversationId, getOrCreateConversationId, loadLocalConversations, makersConversationHeaders, mergeMessages, saveLocalConversations, setActiveConversationId } from './conversation';

describe('getOrCreateConversationId', () => {
  beforeEach(() => {
    const values = new Map<string, string>();
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
      clear: () => values.clear(),
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
});

describe('mergeMessages', () => {
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
});
