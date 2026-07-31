import test from 'node:test';
import assert from 'node:assert/strict';

import {
  handleLogout,
  handleSession,
} from './session-controller.js';
import {
  handleWechatCallback,
  handleWechatStart,
} from './wechat-controller.js';
import {
  authenticatedRequest,
  TEST_AUTH_ENV,
  testIdentity,
} from '../../test-utils/auth.js';

test('session Controller creates an isolated guest and then reuses its signed cookie', async () => {
  const created = await handleSession({
    request: new Request('https://example.com/auth/session'),
    env: TEST_AUTH_ENV,
  });
  assert.equal(created.status, 200);
  const first = await created.json();
  assert.equal(first.identity.auth_type, 'guest');
  assert.equal(first.identity.membership, 'guest');
  assert.equal(first.login.wechat_available, false);
  assert.match(first.identity.id, /^floris:/);
  const cookie = created.headers.get('set-cookie').split(';', 1)[0];
  const reused = await handleSession({
    request: new Request('https://example.com/auth/session', {
      headers: { Cookie: cookie },
    }),
    env: TEST_AUTH_ENV,
  });
  assert.equal((await reused.json()).identity.id, first.identity.id);
});

test('session Controller fails closed when the signing secret is unavailable', async () => {
  const response = await handleSession({
    request: new Request('https://example.com/auth/session'),
    env: {},
  });
  assert.equal(response.status, 503);
  assert.deepEqual(await response.json(), {
    error: 'Authentication is not configured',
    code: 'AUTH_NOT_CONFIGURED',
  });
});

test('session Controller exposes WeChat only when OAuth and identity storage are ready', async () => {
  const incomplete = await handleSession({
    request: new Request('https://example.com/auth/session'),
    env: {
      ...TEST_AUTH_ENV,
      WECHAT_OPEN_APP_ID: 'wx-test-app',
      WECHAT_OPEN_APP_SECRET: 'server-only-secret',
    },
  });
  assert.equal((await incomplete.json()).login.wechat_available, false);

  const ready = await handleSession({
    request: new Request('https://example.com/auth/session'),
    env: {
      ...TEST_AUTH_ENV,
      WECHAT_OPEN_APP_ID: 'wx-test-app',
      WECHAT_OPEN_APP_SECRET: 'server-only-secret',
      DATABASE_URL: 'postgresql://example.invalid/floris',
    },
  });
  assert.equal((await ready.json()).login.wechat_available, true);
});

test('logout Controller expires only the signed browser session', async () => {
  const response = await handleLogout({
    request: new Request('https://example.com/auth/logout', { method: 'POST' }),
  });
  assert.equal(response.status, 200);
  assert.match(response.headers.get('set-cookie'), /Max-Age=0/);
});

test('WeChat start Controller preserves guest continuity in signed OAuth state', async () => {
  const request = await authenticatedRequest(
    'https://example.com/auth/wechat/start?return_to=%2FchatBot',
    {},
    testIdentity({
      auth_type: 'guest',
      membership: 'guest',
      roles: ['guest'],
    }),
    TEST_AUTH_ENV,
  );
  const response = await handleWechatStart({
    request,
    env: {
      ...TEST_AUTH_ENV,
      WECHAT_OPEN_APP_ID: 'wx-test-app',
    },
  });
  assert.equal(response.status, 302);
  assert.match(response.headers.get('location'), /^https:\/\/open\.weixin\.qq\.com\//);
  assert.match(response.headers.get('set-cookie'), /floris_oauth_nonce=/);
});

test('WeChat callback Controller rejects an incomplete callback before provider access', async () => {
  const response = await handleWechatCallback({
    request: new Request('https://example.com/auth/wechat/callback'),
    env: TEST_AUTH_ENV,
  });
  assert.equal(response.status, 400);
});
