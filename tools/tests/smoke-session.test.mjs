import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createSmokeClient,
  createSmokeConversationId,
} from '../smoke-session.mjs';


function sessionBody(authType = 'guest') {
  return {
    identity: {
      id: `tenant:${authType}`,
      auth_type: authType,
      membership: authType === 'guest' ? 'guest' : 'free',
    },
    entitlements: { plan: authType === 'guest' ? 'guest' : 'free' },
    login: { cloudbase_available: true },
  };
}


test('bootstraps a signed guest Cookie before protected smoke requests', async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init });
    if (calls.length === 1) {
      return new Response(JSON.stringify(sessionBody()), {
        status: 200,
        headers: {
          'Content-Type': 'application/json',
          'Set-Cookie': 'floris_session=signed-guest; Path=/; HttpOnly; Secure',
        },
      });
    }
    return new Response('{}', { status: 200 });
  };

  const client = await createSmokeClient({
    baseUrl: 'https://dev.example.test/',
    authQuery: 'eo_token=preview&eo_time=123',
    fetchImpl,
    env: {},
  });
  await client.fetch('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });

  assert.equal(client.auth.transport, 'cookie');
  assert.equal(client.auth.auth_type, 'guest');
  assert.equal(calls[0].url, 'https://dev.example.test/auth/session?eo_token=preview&eo_time=123');
  assert.equal(calls[1].init.headers.get('Cookie'), 'floris_session=signed-guest');
  assert.equal(calls[1].init.headers.get('Content-Type'), 'application/json');
});


test('uses the native Bearer contract and never converts it into a Cookie', async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init });
    return new Response(JSON.stringify(sessionBody('cloudbase')), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Set-Cookie': 'floris_session=must-not-be-used; Path=/',
      },
    });
  };

  const client = await createSmokeClient({
    baseUrl: 'https://dev.example.test',
    fetchImpl,
    env: {
      FLORIS_SMOKE_BEARER_TOKEN: 'short-lived-native-token',
      FLORIS_SMOKE_REQUIRE_LOGIN: '1',
    },
  });
  await client.fetch('/workspace', { method: 'POST' });

  assert.equal(client.auth.transport, 'bearer');
  assert.equal(client.auth.auth_type, 'cloudbase');
  assert.equal(calls[0].init.headers.get('Authorization'), 'Bearer short-lived-native-token');
  assert.equal(calls[1].init.headers.get('Authorization'), 'Bearer short-lived-native-token');
  assert.equal(calls[1].init.headers.get('Cookie'), null);
});


test('fails closed when a login-state smoke receives only a guest identity', async () => {
  const fetchImpl = async () => new Response(JSON.stringify(sessionBody()), {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      'Set-Cookie': 'floris_session=signed-guest; Path=/',
    },
  });

  await assert.rejects(
    createSmokeClient({
      baseUrl: 'https://dev.example.test',
      fetchImpl,
      env: { FLORIS_SMOKE_REQUIRE_LOGIN: 'true' },
    }),
    /returned a guest identity/,
  );
});


test('validates a caller-supplied Web session and adopts its renewal', async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init });
    return new Response(JSON.stringify(sessionBody('cloudbase')), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Set-Cookie': 'floris_session=renewed-session; Path=/; HttpOnly',
      },
    });
  };

  const client = await createSmokeClient({
    baseUrl: 'https://dev.example.test',
    fetchImpl,
    env: {
      FLORIS_SMOKE_SESSION_COOKIE: 'floris_session=existing-session; Path=/',
      FLORIS_SMOKE_REQUIRE_LOGIN: 'yes',
    },
  });
  await client.fetch('/messages', { method: 'POST' });

  assert.equal(calls[0].init.headers.get('Cookie'), 'floris_session=existing-session');
  assert.equal(calls[1].init.headers.get('Cookie'), 'floris_session=renewed-session');
});


test('creates conversation ids inside the Maker 6-36 character contract', () => {
  const id = createSmokeConversationId(
    'Skill timeline label that is deliberately much too long',
    '第 12 轮',
  );
  assert.match(id, /^[0-9a-zA-Z-_.]{6,36}$/);
  assert.ok(id.startsWith('smk-skill-timeline-'));
});
