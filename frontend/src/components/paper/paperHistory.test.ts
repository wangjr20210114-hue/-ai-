import { describe, expect, it } from 'vitest';
import type { PaperAssistantResult } from '../../services/paperApi';
import { newestTranslationsFirst } from './paperHistory';

function result(
  id: string,
  createdAt: number,
  action: PaperAssistantResult['action'] = 'translate',
): PaperAssistantResult {
  return {
    id,
    action,
    title: id,
    source_text: 'source',
    content: 'translated',
    created_at: createdAt,
  };
}

describe('paper translation history', () => {
  it('shows the newest translation first and excludes other assistant actions', () => {
    expect(newestTranslationsFirst([
      result('older', 10),
      result('analysis', 30, 'analyze'),
      result('newest', 20),
    ]).map((item) => item.id)).toEqual(['newest', 'older']);
  });
});
