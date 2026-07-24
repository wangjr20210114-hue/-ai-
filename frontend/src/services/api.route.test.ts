import { afterEach, describe, expect, it, vi } from 'vitest';
import { planMakersRoute, resetApplicationData } from './api';
import type { MakersMapPlace, MakersRoutePlan } from '../types';

afterEach(() => vi.unstubAllGlobals());

describe('planMakersRoute', () => {
  it('sends the calendar order unchanged and disables route optimization', async () => {
    const places: MakersMapPlace[] = [
      { place_id: 'breakfast', name: '早餐店', address: '早餐店', latitude: 40.05, longitude: 116.30 },
      { place_id: 'station', name: '北京站', address: '北京站', latitude: 39.90, longitude: 116.43 },
      { place_id: 'hotel', name: '锦江之星', address: '锦江之星', latitude: 39.91, longitude: 116.27 },
    ];
    const route: MakersRoutePlan = {
      schema_version: 2,
      provider: 'test',
      mode: 'driving',
      places,
      path: [],
      distance_meters: 1,
      duration_seconds: 1,
      fare: {
        currency: 'CNY',
        basis: 'test',
        self_driving: { estimate: 0, toll: 0 },
        taxi: { low: 0, high: 0 },
      },
    };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ route }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);

    await planMakersRoute('test-conversation', places);

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    const body = JSON.parse(String(init.body)) as { places: MakersMapPlace[]; optimize: boolean };
    expect(body.places.map((item) => item.name)).toEqual(['早餐店', '北京站', '锦江之星']);
    expect(body.optimize).toBe(false);
  });
});

describe('resetApplicationData', () => {
  it('requires both Makers state and Blob data to be cleared', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        ok: true,
        conversation_ids: ['yb7_one', 'yb7_two', 'yb7_three'],
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        ok: true,
        state_items_deleted: 9,
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        ok: true,
        conversations_deleted: 3,
        deleted: { 'yuanbao-files': 4, 'yuanbao-acceptance-shared': 2, 'yuanbao-auth': 1 },
      }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(resetApplicationData('yb7_reset-test', 'secret')).resolves.toEqual({
      conversations_deleted: 3,
      state_items_deleted: 9,
      files_deleted: 7,
    });
    expect(fetchMock.mock.calls.map((item) => item[0])).toEqual(['/reset-files', '/reset', '/reset-files']);
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({
      password: 'secret',
      operation: 'inspect',
    });
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({
      password: 'secret',
      conversation_ids: ['yb7_one', 'yb7_two', 'yb7_three'],
    });
    expect(JSON.parse(String(fetchMock.mock.calls[2][1]?.body))).toEqual({
      password: 'secret',
      operation: 'clear',
    });
  });

  it('does not delete conversations until Makers checkpoints and state are cleared', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        ok: true,
        conversation_ids: ['yb7_history'],
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        ok: true,
        state_items_deleted: 4,
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        ok: true,
        conversations_deleted: 1,
        deleted: {},
      }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(resetApplicationData('yb7_reset-test', 'secret')).resolves.toMatchObject({
      conversations_deleted: 1,
      state_items_deleted: 4,
    });
    expect(fetchMock.mock.calls.map((item) => JSON.parse(String(item[1]?.body)).operation || 'state'))
      .toEqual(['inspect', 'state', 'clear']);
  });

  it('exposes a stable error code instead of a server message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      error: 'internal wording',
      code: 'INVALID_PASSWORD',
    }), { status: 403 })));
    await expect(resetApplicationData('yb7_reset-test', 'wrong')).rejects.toMatchObject({
      code: 'INVALID_PASSWORD',
    });
  });
});
