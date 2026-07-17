import { describe, expect, it } from 'vitest';
import { followUpDraftAction } from './followUps';

describe('followUpDraftAction', () => {
  it('fills the composer without creating or sending a user message', () => {
    expect(followUpDraftAction('故宫为什么叫紫禁城？')).toEqual({
      type: 'SET_DRAFT',
      payload: '故宫为什么叫紫禁城？',
    });
  });
});
