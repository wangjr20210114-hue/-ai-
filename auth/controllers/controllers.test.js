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
import {
  oauthNonceCookie,
  signSessionToken,
  verifySessionToken,
} from '../session.js';

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
  assert.equal(first.login.wechat_mode, 'qr');
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
  const desktopLogin = (await ready.json()).login;
  assert.equal(desktopLogin.wechat_available, true);
  assert.equal(desktopLogin.wechat_mode, 'qr');

  const wechatWithoutOfficialAccount = await handleSession({
    request: new Request('https://example.com/auth/session', {
      headers: { 'User-Agent': 'Mozilla/5.0 MicroMessenger/8.0.50' },
    }),
    env: {
      ...TEST_AUTH_ENV,
      WECHAT_OPEN_APP_ID: 'wx-test-app',
      WECHAT_OPEN_APP_SECRET: 'server-only-secret',
      DATABASE_URL: 'postgresql://example.invalid/floris',
    },
  });
  const missingInAppLogin = (await wechatWithoutOfficialAccount.json()).login;
  assert.equal(missingInAppLogin.wechat_available, false);
  assert.equal(missingInAppLogin.wechat_mode, 'in_app');

  const wechatReady = await handleSession({
    request: new Request('https://example.com/auth/session', {
      headers: { 'User-Agent': 'Mozilla/5.0 MicroMessenger/8.0.50' },
    }),
    env: {
      ...TEST_AUTH_ENV,
      WECHAT_OFFICIAL_ACCOUNT_APP_ID: 'wx-official-account',
      WECHAT_OFFICIAL_ACCOUNT_APP_SECRET: 'official-secret',
      DATABASE_URL: 'postgresql://example.invalid/floris',
    },
  });
  const inAppLogin = (await wechatReady.json()).login;
  assert.equal(inAppLogin.wechat_available, true);
  assert.equal(inAppLogin.wechat_mode, 'in_app');
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
      WECHAT_OPEN_APP_SECRET: 'server-only-secret',
      DATABASE_URL: 'postgresql://example.invalid/floris',
    },
  });
  assert.equal(response.status, 302);
  const location = new URL(response.headers.get('location'));
  assert.equal(location.pathname, '/connect/qrconnect');
  assert.equal(location.searchParams.get('appid'), 'wx-test-app');
  assert.equal(location.searchParams.get('scope'), 'snsapi_login');
  const state = await verifySessionToken(location.searchParams.get('state'), TEST_AUTH_ENV, {
    purpose: 'wechat_oauth_state',
  });
  assert.equal(state.wechat_login_mode, 'qr');
  assert.equal(state.guest_subject, testIdentity().sub);
  assert.match(response.headers.get('set-cookie'), /floris_oauth_nonce=/);
});

test('WeChat start Controller uses in-app OAuth only for a signed WeChat-browser flow', async () => {
  const request = await authenticatedRequest(
    'https://example.com/auth/wechat/start?return_to=%2FchatBot',
    { headers: { 'User-Agent': 'Mozilla/5.0 MicroMessenger/8.0.50' } },
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
      DATABASE_URL: 'postgresql://example.invalid/floris',
      WECHAT_OFFICIAL_ACCOUNT_APP_ID: 'wx-official-account',
      WECHAT_OFFICIAL_ACCOUNT_APP_SECRET: 'official-secret',
    },
  });
  assert.equal(response.status, 302);
  const location = new URL(response.headers.get('location'));
  assert.equal(location.pathname, '/connect/oauth2/authorize');
  assert.equal(location.searchParams.get('appid'), 'wx-official-account');
  assert.equal(location.searchParams.get('scope'), 'snsapi_userinfo');
  const state = await verifySessionToken(location.searchParams.get('state'), TEST_AUTH_ENV, {
    purpose: 'wechat_oauth_state',
  });
  assert.equal(state.wechat_login_mode, 'in_app');
});

test('WeChat callback Controller rejects an incomplete callback before provider access', async () => {
  const response = await handleWechatCallback({
    request: new Request('https://example.com/auth/wechat/callback'),
    env: TEST_AUTH_ENV,
  });
  assert.equal(response.status, 400);
});

test('WeChat callback Controller never switches credentials based on callback User-Agent', async () => {
  const nonce = 'fixed-test-nonce';
  const state = await signSessionToken({
    purpose: 'wechat_oauth_state',
    nonce,
    return_to: '/chatBot',
    wechat_login_mode: 'qr',
  }, TEST_AUTH_ENV, 600);
  const response = await handleWechatCallback({
    request: new Request(`https://example.com/auth/wechat/callback?code=test&state=${state}`, {
      headers: {
        Cookie: oauthNonceCookie(nonce, { secure: false }).split(';', 1)[0],
        'User-Agent': 'Mozilla/5.0 MicroMessenger/8.0.50',
      },
    }),
    env: {
      ...TEST_AUTH_ENV,
      DATABASE_URL: 'postgresql://example.invalid/floris',
      WECHAT_OFFICIAL_ACCOUNT_APP_ID: 'wx-official-account',
      WECHAT_OFFICIAL_ACCOUNT_APP_SECRET: 'official-secret',
    },
  });
  assert.equal(response.status, 503);
  assert.equal((await response.json()).error, 'WeChat login is not configured');
});
