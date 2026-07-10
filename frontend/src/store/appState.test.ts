import { describe, expect, it } from 'vitest';
import { initialState, reducer } from './appState';
import type { ChatMessage } from '../types';

const userMessage: ChatMessage = {
  id: 'msg-1',
  role: 'user',
  content: 'hello',
  ts: 1,
};

describe('app state reducer', () => {
  it('adds and updates a streamed message without mutating previous state', () => {
    const withMessage = reducer(initialState, { type: 'ADD_MESSAGE', payload: userMessage });
    const updated = reducer(withMessage, {
      type: 'UPDATE_MESSAGE',
      payload: { id: 'msg-1', patch: { streaming: true }, delta: ' world' },
    });

    expect(initialState.messages).toHaveLength(0);
    expect(updated.messages[0]).toMatchObject({ content: 'hello world', streaming: true });
  });

  it('clears every streaming flag after a connection-level failure', () => {
    const state = {
      ...initialState,
      messages: [{ ...userMessage, streaming: true }],
    };

    const updated = reducer(state, { type: 'CLEAR_ALL_STREAMING', payload: {} });
    expect(updated.messages[0].streaming).toBe(false);
  });

  it('hydrates persisted messages for the stable local conversation', () => {
    const restored = [{ ...userMessage, id: 'restored', content: 'after restart' }];
    const updated = reducer(initialState, { type: 'HYDRATE_MESSAGES', payload: restored });

    expect(updated.userId).toBe('local-user');
    expect(updated.conversationId).toBe('default-conversation');
    expect(updated.messages[0].content).toBe('after restart');
  });
});
