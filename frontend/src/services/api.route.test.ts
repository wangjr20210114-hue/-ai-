import { afterEach, describe, expect, it, vi } from 'vitest';
import { planMakersRoute } from './api';
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
