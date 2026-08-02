import test from 'node:test';
import assert from 'node:assert/strict';

import { middleware } from './middleware.js';

test('middleware rejects a protected request without a session cookie', async () => {
  let delegated = false;
  const response = await middleware({
    request: new Request('https://example.com/messages'),
    next: async () => {
      delegated = true;
      return new Response('unexpected');
    },
  });

  assert.equal(response.status, 401);
  assert.equal(delegated, false);
  assert.deepEqual(await response.json(), {
    error: 'Authentication session is required',
    code: 'UNAUTHORIZED',
  });
});

test('middleware delegates signature verification to the trusted route controller', async () => {
  let delegated = false;
  const response = await middleware({
    request: new Request('https://example.com/messages', {
      headers: { Cookie: 'floris_session=controller-verifies-this-token' },
    }),
    next: async () => {
      delegated = true;
      return new Response('delegated');
    },
  });

  assert.equal(response.status, 200);
  assert.equal(await response.text(), 'delegated');
  assert.equal(delegated, true);
});

test('middleware delegates native Bearer verification to the trusted route controller', async () => {
  let delegated = false;
  const response = await middleware({
    request: new Request('https://example.com/messages', {
      headers: { Authorization: 'Bearer controller-verifies-this-token' },
    }),
    next: async () => {
      delegated = true;
      return new Response('delegated');
    },
  });

  assert.equal(response.status, 200);
  assert.equal(delegated, true);
});

test('public authentication routes remain available before a session exists', async () => {
  const response = await middleware({
    request: new Request('https://example.com/auth/session'),
    next: async () => new Response('public'),
  });

  assert.equal(response.status, 200);
  assert.equal(await response.text(), 'public');
});

test('CloudBase token exchange remains public while its Controller verifies the token', async () => {
  const response = await middleware({
    request: new Request('https://example.com/auth/cloudbase/session', {
      method: 'POST',
    }),
    next: async () => new Response('public'),
  });

  assert.equal(response.status, 200);
  assert.equal(await response.text(), 'public');
});

test('mobile CloudBase exchange remains public before a Floris Bearer exists', async () => {
  const response = await middleware({
    request: new Request('https://example.com/auth/mobile/session', {
      method: 'POST',
    }),
    next: async () => new Response('public'),
  });

  assert.equal(response.status, 200);
  assert.equal(await response.text(), 'public');
});
