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

  it('records the calendar target for the write confirmation animation', () => {
    const updated = reducer(initialState, {
      type: 'PULSE_CALENDAR',
      payload: { date: '2026-07-15', count: 4 },
    });

    expect(updated.calendarPulse).toMatchObject({ date: '2026-07-15', count: 4 });
    expect(updated.calendarFocusDate).toBe('2026-07-15');
    expect(updated.calendarPulse?.token).toBeTypeOf('number');
  });

  it('restores the calendar date without replaying the write animation', () => {
    const updated = reducer(initialState, {
      type: 'FOCUS_CALENDAR',
      payload: '2026-07-15',
    });

    expect(updated.calendarFocusDate).toBe('2026-07-15');
    expect(updated.calendarPulse).toBeNull();
  });

  it('merges travel-plan schedules immediately by id', () => {
    const schedule = {
      id: 'travel-tiananmen', session_id: 'user-a', title: '天安门广场',
      category: 'travel' as const, start_time: 1784077200, duration_minutes: 120,
      duration_days: 0, location: '北京市东城区', description: '', markdown_content: '',
      extra: {}, done: false, created_at: 1, updated_at: 1,
    };
    const first = reducer(initialState, { type: 'MERGE_SCHEDULES', payload: [schedule] });
    const updated = reducer(first, {
      type: 'MERGE_SCHEDULES',
      payload: [{ ...schedule, title: '天安门广场（已更新）' }],
    });

    expect(updated.schedules).toHaveLength(1);
    expect(updated.schedules[0].title).toBe('天安门广场（已更新）');
  });

  it('stores verified recommendation coordinates for the map animation', () => {
    const updated = reducer(initialState, {
      type: 'SET_MAP_PLACES',
      payload: {
        title: '北京推荐地点',
        places: [{ name: '故宫博物院', address: '北京市东城区', lat: 39.9163, lng: 116.3972 }],
      },
    });

    expect(updated.mapTitle).toBe('北京推荐地点');
    expect(updated.recommendedPlaces[0].name).toBe('故宫博物院');
    expect(updated.mapRevision).toBe(initialState.mapRevision + 1);
  });
});
