import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getOrCreateConversationId, makersConversationHeaders } from './conversation';

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
    const first = getOrCreateConversationId(true);
    const second = getOrCreateConversationId(true);
    expect(first).toBe(second);
    expect(first.length).toBeGreaterThan(10);
  });

  it('migrates the first EdgeOne branch legacy key', () => {
    localStorage.setItem('eo_conv_id', 'legacy-conversation');
    expect(getOrCreateConversationId(true)).toBe('legacy-conversation');
    expect(localStorage.getItem('yuanbao.conversationId')).toBe('legacy-conversation');
  });

  it('uses the backend default conversation in local mode', () => {
    localStorage.setItem('yuanbao.conversationId', 'makers-conversation');
    expect(getOrCreateConversationId(false)).toBe('default-conversation');
  });

  it('uses the Makers conversation header for every agent endpoint', () => {
    expect(makersConversationHeaders('conversation-123')).toEqual({
      'makers-conversation-id': 'conversation-123',
    });
  });
});
