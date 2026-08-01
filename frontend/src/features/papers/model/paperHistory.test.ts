import { describe, expect, it } from 'vitest';
import type { PaperAssistantResult } from './types';
import { translationsInTimeOrder } from './paperHistory';

describe('translationsInTimeOrder', () => {
  it('keeps only translations and appends the newest translation last', () => {
    const results: PaperAssistantResult[] = [
      { id: 'new', action: 'translate', title: 'new', source_text: '', content: 'new', created_at: 30 },
      { id: 'analysis', action: 'analyze', title: 'analysis', source_text: '', content: 'analysis', created_at: 20 },
      { id: 'old', action: 'translate', title: 'old', source_text: '', content: 'old', created_at: 10 },
    ];

    expect(translationsInTimeOrder(results).map((item) => item.id)).toEqual(['old', 'new']);
  });
});
