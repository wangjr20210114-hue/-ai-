import { afterEach, describe, expect, it, vi } from 'vitest';
import { getProviderUsage, planMakersRoute, resetApplicationData } from './apiComposition';
import type { MakersMapPlace, MakersRoutePlan } from '../shared/types';

afterEach(() => vi.unstubAllGlobals());

const TEST_AUTH_SESSION = {
  identity: {
    id: 'test:test-user',
    subject_id: 'test-user',
    tenant_id: 'test',
    username: 'tester',
    display_name: 'Tester',
    avatar_url: '',
    auth_type: 'wechat',
    membership: 'free',
    roles: ['user'],
  },
  entitlements: {
    plan: 'free',
    limits: {},
    payment_available: false,
  },
  login: {
    wechat_available: true,
    wechat_start_url: '/auth/wechat/start',
    logout_url: '/auth/logout',
  },
};

function authenticatedFetch(
  handler: (input: RequestInfo | URL, init?: RequestInit) => Response | Promise<Response>,
) {
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).startsWith('/auth/session')) {
      return Promise.resolve(new Response(JSON.stringify(TEST_AUTH_SESSION), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }));
    }
    return Promise.resolve(handler(input, init));
  });
}

function applicationCalls(fetchMock: ReturnType<typeof authenticatedFetch>) {
  return fetchMock.mock.calls.filter(([input]) => !String(input).startsWith('/auth/session'));
}

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
    const fetchMock = authenticatedFetch(() => new Response(JSON.stringify({ route }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);

    await planMakersRoute('test-conversation', places, 'walking', 'least_time');

    const init = applicationCalls(fetchMock)[0][1] as RequestInit;
    const body = JSON.parse(String(init.body)) as { places: MakersMapPlace[]; optimize: boolean; mode: string; strategy: string };
    expect(body.places.map((item) => item.name)).toEqual(['早餐店', '北京站', '锦江之星']);
    expect(body.optimize).toBe(false);
    expect(body.mode).toBe('walking');
    expect(body.strategy).toBe('least_time');
  });
});

describe('getProviderUsage', () => {
  it('accepts a safe provider usage summary', async () => {
    const payload = {
      refreshed_at: 2_000_000_000,
      usage: {
        daily_tokens: 120,
        monthly_tokens: 340,
        preferences: { daily_token_limit: 0, monthly_token_limit: 0, enforcement: 'off' },
        alerts: { daily: false, monthly: false },
      },
      metering: {
        daily: { 'wsa.requests': 2 },
        monthly: { 'wsa.requests': 9 },
        providers: { wsa: { daily_requests: 2, monthly_requests: 9 } },
        recorded_events: 9,
        timezone: 'Asia/Shanghai',
      },
      providers: [],
    };
    vi.stubGlobal('fetch', authenticatedFetch(
      () => new Response(JSON.stringify(payload), { status: 200 }),
    ));
    await expect(getProviderUsage('yb7_provider-usage')).resolves.toEqual(payload);
  });

  it('rejects an HTML fallback or malformed 200 response instead of crashing settings', async () => {
    vi.stubGlobal('fetch', authenticatedFetch(() => new Response('<!doctype html>', {
      status: 200,
      headers: { 'content-type': 'text/html' },
    })));
    await expect(getProviderUsage('yb7_provider-usage')).rejects.toThrow();
  });
});

describe('resetApplicationData', () => {
  it('requires both Makers state and Blob data to be cleared', async () => {
    const responses = [
      new Response(JSON.stringify({
        ok: true,
        conversation_ids: ['yb7_one', 'yb7_two', 'yb7_three'],
      }), { status: 200 }),
      new Response(JSON.stringify({
        ok: true,
        state_items_deleted: 9,
      }), { status: 200 }),
      new Response(JSON.stringify({
        ok: true,
        conversations_deleted: 3,
        deleted: { 'yuanbao-files': 4, 'yuanbao-acceptance-shared': 2, 'yuanbao-auth': 1 },
      }), { status: 200 }),
    ];
    const fetchMock = authenticatedFetch(() => responses.shift()!);
    vi.stubGlobal('fetch', fetchMock);

    await expect(resetApplicationData('yb7_reset-test', 'secret')).resolves.toEqual({
      conversations_deleted: 3,
      state_items_deleted: 9,
      files_deleted: 7,
    });
    const calls = applicationCalls(fetchMock);
    expect(calls.map((item) => item[0])).toEqual(['/reset-files', '/reset', '/reset-files']);
    expect(JSON.parse(String(calls[0][1]?.body))).toEqual({
      confirmation: 'secret',
      operation: 'inspect',
    });
    expect(JSON.parse(String(calls[1][1]?.body))).toEqual({
      confirmation: 'secret',
      conversation_ids: ['yb7_one', 'yb7_two', 'yb7_three'],
    });
    expect(JSON.parse(String(calls[2][1]?.body))).toEqual({
      confirmation: 'secret',
      operation: 'clear',
    });
  });

  it('does not delete conversations until Makers checkpoints and state are cleared', async () => {
    const responses = [
      new Response(JSON.stringify({
        ok: true,
        conversation_ids: ['yb7_history'],
      }), { status: 200 }),
      new Response(JSON.stringify({
        ok: true,
        state_items_deleted: 4,
      }), { status: 200 }),
      new Response(JSON.stringify({
        ok: true,
        conversations_deleted: 1,
        deleted: {},
      }), { status: 200 }),
    ];
    const fetchMock = authenticatedFetch(() => responses.shift()!);
    vi.stubGlobal('fetch', fetchMock);

    await expect(resetApplicationData('yb7_reset-test', 'secret')).resolves.toMatchObject({
      conversations_deleted: 1,
      state_items_deleted: 4,
    });
    expect(applicationCalls(fetchMock).map((item) => JSON.parse(String(item[1]?.body)).operation || 'state'))
      .toEqual(['inspect', 'state', 'clear']);
  });

  it('exposes a stable error code instead of a server message', async () => {
    vi.stubGlobal('fetch', authenticatedFetch(() => new Response(JSON.stringify({
      error: 'internal wording',
      code: 'INVALID_CONFIRMATION',
    }), { status: 403 })));
    await expect(resetApplicationData('yb7_reset-test', 'wrong')).rejects.toMatchObject({
      code: 'INVALID_CONFIRMATION',
    });
  });
});
