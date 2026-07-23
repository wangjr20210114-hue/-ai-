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

  it('switches to fresh chat memory while retaining user-owned workspace assets', () => {
    const previous = {
      ...initialState,
      connected: true,
      thinking: true,
      draft: 'unfinished',
      messages: [userMessage],
      mapPlaces: [{ place_id: 'old', name: '旧地点', address: '', latitude: 1, longitude: 1 }],
      documentContext: { fileId: 'uploads/test.pdf', filename: 'test.pdf', text: 'test body' },
    };

    const next = reducer(previous, { type: 'SET_CONVERSATION_ID', payload: 'conv-fresh' });

    expect(next.conversationId).toBe('conv-fresh');
    expect(next.connected).toBe(false);
    expect(next.thinking).toBe(false);
    expect(next.draft).toBe('');
    expect(next.messages).toEqual([]);
    expect(next.documentContext).toBeNull();
    expect(next.mapPlaces).toEqual(previous.mapPlaces);
  });

  it('holds a selected document only until the composer clears it', () => {
    const context = { fileId: 'uploads/test.pdf', filename: 'test.pdf', text: 'test body' };
    const selected = reducer(initialState, { type: 'SET_DOCUMENT_CONTEXT', payload: context });
    const cleared = reducer(selected, { type: 'SET_DOCUMENT_CONTEXT', payload: null });
    expect(selected.documentContext).toEqual(context);
    expect(cleared.documentContext).toBeNull();
  });

  it('orders newly updated conversations before older history', () => {
    const oldConversation = {
      id: 'old', title: '旧对话', createdAt: 1, updatedAt: 1, messageCount: 2,
    };
    const recentConversation = {
      id: 'recent', title: '新对话', createdAt: 2, updatedAt: 3, messageCount: 0,
    };
    const withOld = reducer(initialState, { type: 'SET_CONVERSATIONS', payload: [oldConversation] });
    const updated = reducer(withOld, { type: 'UPSERT_CONVERSATION', payload: recentConversation });

    expect(updated.conversations.map((item) => item.id)).toEqual(['recent', 'old']);
  });

  it('merges persisted Makers calendar events without duplicating ids', () => {
    const event = {
      id: 'makers-event-1',
      session_id: 'makers',
      title: '参观故宫',
      category: 'travel' as const,
      start_time: 1784073600,
      duration_minutes: 120,
      duration_days: 0,
      location: '故宫博物院',
      description: '',
      markdown_content: '',
      extra: {},
      done: false,
      created_at: 1,
      updated_at: 1,
    };
    const first = reducer(initialState, { type: 'MERGE_SCHEDULES', payload: [event] });
    const second = reducer(first, {
      type: 'MERGE_SCHEDULES',
      payload: [{ ...event, title: '参观故宫（更新）' }],
    });

    expect(second.schedules).toHaveLength(1);
    expect(second.schedules[0].title).toBe('参观故宫（更新）');
  });

  it('updates map places and increments the animation revision', () => {
    const updated = reducer(initialState, {
      type: 'SET_MAP_PLACES',
      payload: {
        title: '故宫路线',
        places: [{ place_id: 'poi-wumen', name: '午门', address: '北京市东城区', latitude: 39.912, longitude: 116.397 }],
      },
    });

    expect(updated.mapTitle).toBe('故宫路线');
    expect(updated.mapPlaces[0].name).toBe('午门');
    expect(updated.mapRevision).toBe(initialState.mapRevision + 1);
  });

  it('keeps the map persistent across identical checkpoint snapshots', () => {
    const places = [{
      place_id: 'poi-wumen', provider: 'tencent', name: '午门', address: '北京市东城区',
      latitude: 39.912, longitude: 116.397,
    }];
    const activated = reducer(initialState, {
      type: 'SET_MAP_PLACES', payload: { title: '故宫路线', places },
    });
    const snapshot = reducer(activated, {
      type: 'HYDRATE_WORKSPACE',
      payload: { schedules: [], mapPlaces: [{ ...places[0] }], mapTitle: '故宫路线' },
    });
    const transportOnlySnapshot = reducer(snapshot, {
      type: 'HYDRATE_WORKSPACE', payload: { schedules: [] },
    });

    expect(snapshot.mapPlaces).toBe(activated.mapPlaces);
    expect(snapshot.mapRevision).toBe(activated.mapRevision);
    expect(transportOnlySnapshot.mapPlaces).toBe(activated.mapPlaces);
    expect(transportOnlySnapshot.mapTitle).toBe('故宫路线');
    expect(transportOnlySnapshot.mapRevision).toBe(activated.mapRevision);
  });

  it('reveals the same saved map again after an explicit action click', () => {
    const places = [{
      place_id: 'poi-wumen', provider: 'tencent', name: '午门', address: '北京市东城区',
      latitude: 39.912, longitude: 116.397,
    }];
    const activated = reducer(initialState, {
      type: 'SET_MAP_PLACES', payload: { title: '故宫路线', places },
    });
    const revealedAgain = reducer(activated, {
      type: 'SET_MAP_PLACES', payload: { title: '故宫路线', places: [{ ...places[0] }], reveal: true },
    });

    expect(revealedAgain.mapPlaces).toBe(activated.mapPlaces);
    expect(revealedAgain.mapRevision).toBe(activated.mapRevision + 1);
  });

  it('hydrates the persistent proactive inbox independently from conversations', () => {
    const proactive = {
      schema_version: 1,
      revision: 3,
      preferences: {
        enabled: true,
        autonomy_mode: 'propose' as const,
        timezone: 'Asia/Shanghai',
        quiet_hours: { enabled: true, start: '22:00', end: '08:00' },
        daily_limit: 5,
        lookahead_hours: 24,
        window_limit: 4,
        types: { schedule_upcoming: true },
      },
      notifications: [],
      runs: [],
      workflows: [],
      checkpoints: {},
      last_tick: null,
    };
    const hydrated = reducer(initialState, { type: 'HYDRATE_PROACTIVE', payload: proactive });
    const switched = reducer(hydrated, { type: 'SET_CONVERSATION_ID', payload: 'another' });
    expect(switched.proactive?.revision).toBe(3);
  });
});
