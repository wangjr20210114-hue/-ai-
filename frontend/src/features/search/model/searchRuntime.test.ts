import { describe, expect, it } from 'vitest';

import { restoredPresentationTiming } from './searchRuntime';

describe('restored presentation timing', () => {
  it('uses the original question boundary for an active search', () => {
    expect(restoredPresentationTiming({
      schema_version: 1,
      run_id: 'run',
      client_message_id: 'client',
      revision: 3,
      updated_at: 1786000004000,
      turn_started_at: 1786000000000,
      search_selected: true,
      search_started_at: 1786000000000,
      content: '恢复中的回答',
    }, {}, [], 1786999999999)).toEqual({
      turnStartedAt: 1786000000000,
      searchSelected: true,
      searchStartedAt: 1786000000000,
    });
  });

  it('does not relabel an ordinary chat as search', () => {
    expect(restoredPresentationTiming({
      schema_version: 1,
      run_id: 'run',
      client_message_id: 'client',
      revision: 1,
      updated_at: 1786000001000,
      turn_started_at: 1786000000000,
      content: '',
    }).searchSelected).toBe(false);
  });
});
