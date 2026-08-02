import test from 'node:test';
import assert from 'node:assert/strict';

import { onRequest } from './index.js';
import { signSessionToken, verifySessionToken } from '../../auth/session.js';
import { authenticatedRequest, TEST_AUTH_ENV, testIdentity } from '../../test-utils/auth.js';

const PROFILE_PREFIX = 'tenants/floris/users/11111111-1111-4111-8111-111111111111/profile/';

class FakeStore {
  constructor() {
    this.values = new Map();
    this.metadata = new Map();
  }

  async get(key, options = {}) {
    const value = this.values.get(key) ?? null;
    return options.type === 'json' && value ? structuredClone(value) : value;
  }

  async setJSON(key, value) {
    this.values.set(key, structuredClone(value));
  }

  async getMetadata(key) {
    return this.metadata.get(key) || null;
  }

  async createUploadUrl(key, { contentType }) {
    return { url: 'https://upload.example/avatar', key, contentType };
  }
}

async function call(store, body, request) {
  return onRequest({
    request: request || await authenticatedRequest('https://example.test/profile', {
      method: body ? 'POST' : 'GET',
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined,
    }),
    env: TEST_AUTH_ENV,
    __store: store,
  });
}

test('profile avatar upload and account data stay inside the Maker tenant prefix', async () => {
  const store = new FakeStore();
  const created = await call(store, {
    operation: 'create_avatar_upload',
    content_type: 'image/png',
    size: 2048,
  });
  assert.equal(created.status, 200);
  const upload = await created.json();
  assert.ok(upload.key.startsWith(`${PROFILE_PREFIX}avatars/`));
  store.metadata.set(upload.key, { contentType: 'image/png', size: 2048 });

  const updated = await call(store, {
    operation: 'update',
    display_name: 'Floris Tester',
    avatar_key: upload.key,
  });
  assert.equal(updated.status, 200);
  assert.match(updated.headers.get('set-cookie'), /Max-Age=2592000/);
  const identity = (await updated.json()).identity;
  assert.equal(identity.display_name, 'Floris Tester');
  assert.match(identity.avatar_url, /^\/profile\?avatar_key=/);

  const restored = await call(store);
  assert.equal((await restored.json()).profile.display_name, 'Floris Tester');
});

test('native profile update rotates the short-lived Bearer without setting a cookie', async () => {
  const store = new FakeStore();
  const token = await signSessionToken(testIdentity({ auth_type: 'cloudbase' }), TEST_AUTH_ENV, 600);
  const request = new Request('https://example.test/profile', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ operation: 'update', display_name: 'Native User' }),
  });
  const response = await call(store, null, request);
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('set-cookie'), null);
  const body = await response.json();
  assert.equal(body.token_type, 'Bearer');
  const rotated = await verifySessionToken(body.access_token, TEST_AUTH_ENV);
  assert.equal(rotated.client_kind, 'native');
  assert.equal(rotated.display_name, 'Native User');
});

test('profile rejects an uploaded object that exceeds the avatar limit', async () => {
  const store = new FakeStore();
  const key = `${PROFILE_PREFIX}avatars/oversized.png`;
  store.metadata.set(key, { contentType: 'image/png', size: 5 * 1024 * 1024 + 1 });
  const response = await call(store, {
    operation: 'update',
    display_name: 'Large Avatar',
    avatar_key: key,
  });
  assert.equal(response.status, 400);
  assert.equal((await response.json()).error, 'Avatar upload is incomplete');
});
