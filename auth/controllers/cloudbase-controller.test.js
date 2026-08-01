import test from 'node:test';
import assert from 'node:assert/strict';

import { handleCloudBaseSession } from './cloudbase-controller.js';
import { readCookie, sessionConstants, verifySessionToken } from '../session.js';
import {
  authenticatedRequest,
  TEST_AUTH_ENV,
  testIdentity,
} from '../../test-utils/auth.js';

const CLOUDBASE_UID = 'cloudbase-user-123';
const PERSISTED_USER_ID = '22222222-2222-4222-8222-222222222222';
const GUEST_USER_ID = '11111111-1111-4111-8111-111111111111';

function cloudBaseUser() {
  return {
    sub: CLOUDBASE_UID,
    status: 'ACTIVE',
    email: 'user@example.com',
    user_metadata: {
      name: 'CloudBase User',
      avatar_url: 'https://avatars.example.com/user.png',
    },
    app_metadata: { providers: ['email', 'github'] },
  };
}

function jsonResponse(value, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function accessTokenRequest(origin = 'https://example.com') {
  return new Request('https://example.com/auth/cloudbase/session', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Origin: origin,
    },
    body: JSON.stringify({ access_token: 'cloudbase-access-token' }),
  });
}

test('CloudBase Controller validates the provider token and preserves a guest subject', async (t) => {
  const calls = [];
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    calls.push({ url: String(url), init });
    if (String(url).endsWith('/auth/v1/user/me')) return jsonResponse(cloudBaseUser());
    return jsonResponse([{
      user_id: PERSISTED_USER_ID,
      membership: 'plus',
      roles: ['user'],
    }]);
  });
  const guestRequest = await authenticatedRequest(
    'https://example.com/auth/cloudbase/session',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Origin: 'https://example.com',
      },
      body: JSON.stringify({ access_token: 'cloudbase-access-token' }),
    },
    testIdentity({
      sub: GUEST_USER_ID,
      auth_type: 'guest',
      membership: 'guest',
      roles: ['guest'],
    }),
  );

  const response = await handleCloudBaseSession({
    request: guestRequest,
    env: TEST_AUTH_ENV,
  });
  assert.equal(response.status, 200);
  const body = await response.json();
  assert.equal(body.identity.subject_id, PERSISTED_USER_ID);
  assert.equal(body.identity.membership, 'plus');
  assert.deepEqual(body.identity.auth_providers, ['email', 'github']);
  assert.equal(body.identity_persisted, true);

  assert.equal(calls.length, 2);
  assert.match(calls[0].url, /\/auth\/v1\/user\/me$/);
  assert.equal(calls[0].init.headers.Authorization, 'Bearer cloudbase-access-token');
  const rpcBody = JSON.parse(calls[1].init.body);
  assert.equal(rpcBody.p_candidate_user_id, GUEST_USER_ID);
  assert.equal(rpcBody.p_display_name, 'CloudBase User');

  const cookie = response.headers.get('set-cookie').split(';', 1)[0];
  const token = readCookie(
    new Headers({ Cookie: cookie }),
    sessionConstants.cookieName,
  );
  const session = await verifySessionToken(token, TEST_AUTH_ENV);
  assert.equal(session.sub, PERSISTED_USER_ID);
  assert.equal(session.cloudbase_uid, CLOUDBASE_UID);
  assert.equal(session.auth_type, 'cloudbase');
});

test('CloudBase Controller degrades to the same deterministic subject without the RPC', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url) => {
    if (String(url).endsWith('/auth/v1/user/me')) return jsonResponse(cloudBaseUser());
    return jsonResponse({ code: 'PGRST202' }, 404);
  });

  const subjects = [];
  for (let index = 0; index < 2; index += 1) {
    const response = await handleCloudBaseSession({
      request: accessTokenRequest(),
      env: TEST_AUTH_ENV,
    });
    assert.equal(response.status, 200);
    const body = await response.json();
    assert.equal(body.identity_persisted, false);
    subjects.push(body.identity.subject_id);
  }
  assert.equal(subjects[0], subjects[1]);
  assert.match(subjects[0], /^[0-9a-f]{8}-[0-9a-f]{4}-5[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
});

test('CloudBase Controller rejects cross-origin and invalid provider sessions', async (t) => {
  const crossOrigin = await handleCloudBaseSession({
    request: accessTokenRequest('https://attacker.example'),
    env: TEST_AUTH_ENV,
  });
  assert.equal(crossOrigin.status, 403);

  t.mock.method(globalThis, 'fetch', async () => jsonResponse({
    message: 'invalid token',
  }, 401));
  const rejected = await handleCloudBaseSession({
    request: accessTokenRequest(),
    env: TEST_AUTH_ENV,
  });
  assert.equal(rejected.status, 401);
  assert.equal((await rejected.json()).code, 'INVALID_CLOUDBASE_TOKEN');
});

test('CloudBase Controller trusts browser Fetch Metadata across EdgeOne URL rewriting', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => jsonResponse({
    message: 'invalid token',
  }, 401));

  const sameOrigin = await handleCloudBaseSession({
    request: new Request('https://edgeone-function.internal/auth/cloudbase/session', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Origin: 'https://preview.example.com',
        'Sec-Fetch-Site': 'same-origin',
      },
      body: JSON.stringify({ access_token: 'cloudbase-access-token' }),
    }),
    env: TEST_AUTH_ENV,
  });
  assert.equal(sameOrigin.status, 401);
  assert.equal((await sameOrigin.json()).code, 'INVALID_CLOUDBASE_TOKEN');

  const crossSite = await handleCloudBaseSession({
    request: new Request('https://edgeone-function.internal/auth/cloudbase/session', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Origin: 'https://attacker.example',
        'Sec-Fetch-Site': 'cross-site',
      },
      body: JSON.stringify({ access_token: 'cloudbase-access-token' }),
    }),
    env: TEST_AUTH_ENV,
  });
  assert.equal(crossSite.status, 403);
});
