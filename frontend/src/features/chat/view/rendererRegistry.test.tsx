import { describe, expect, it } from 'vitest';

import type { ChatMessage } from '../../../types';
import { selectRenderer } from './renderers/rendererRegistry';


function message(values: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: 'message-1',
    role: 'ai',
    content: 'answer',
    ts: 1,
    ...values,
  };
}

describe('message renderer registry', () => {
  it('uses deterministic structured priority and a text fallback', () => {
    const search = message({
      searchResults: {
        query: 'q',
        results: [],
        images: [],
        media: [],
        sources_used: [],
        total: 0,
      },
      papers: [{ title: 'paper' } as NonNullable<ChatMessage['papers']>[number]],
    });
    expect(selectRenderer(search).id).toBe('search-evidence');
    expect(selectRenderer(message({
      papers: [{ title: 'paper' } as NonNullable<ChatMessage['papers']>[number]],
    })).id).toBe('paper');
    expect(selectRenderer(message()).id).toBe('text');
  });
});
