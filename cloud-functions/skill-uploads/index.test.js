import test from 'node:test';
import assert from 'node:assert/strict';

import { onRequest } from './index.js';
import {
  authenticatedRequest,
  TEST_AUTH_ENV,
  testIdentity,
} from '../../test-utils/auth.js';

const PREFIX = 'tenants/floris/users/11111111-1111-4111-8111-111111111111/';

class FakeStore {
  constructor() {
    this.values = new Map();
    this.metadata = new Map();
  }

  async list({ prefix = '' } = {}) {
    return {
      blobs: [...this.values.keys()]
        .filter((key) => key.startsWith(prefix))
        .map((key) => ({ key })),
    };
  }

  async get(key) {
    return this.values.get(key) || null;
  }

  async createUploadUrl(key, { contentType }) {
    this.metadata.set(key, { size: 1024, contentType });
    return { url: 'https://upload.example.com/presigned', token: 'one-use-token' };
  }

  async getMetadata(key) {
    return this.metadata.get(key) || null;
  }

  async setJSON(key, value) {
    this.values.set(key, value);
  }
}

async function post(body, identity = testIdentity()) {
  return authenticatedRequest('https://example.com/skill-uploads', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }, identity);
}

test('guest identity cannot upload or execute user Skills', async () => {
  const response = await onRequest({
    request: await post(
      { operation: 'create', name: 'guest.zip', size: 100, content_type: 'application/zip' },
      testIdentity({
        auth_type: 'guest',
        membership: 'guest',
        roles: ['guest'],
      }),
    ),
    env: TEST_AUTH_ENV,
    __store: new FakeStore(),
  });
  assert.equal(response.status, 403);
  assert.equal((await response.json()).code, 'LOGIN_REQUIRED');
});

test('presigned upload and review record remain inside the authenticated tenant prefix', async () => {
  const store = new FakeStore();
  const createResponse = await onRequest({
    request: await post({
      operation: 'create',
      name: '../My unsafe Skill.zip',
      size: 1024,
      content_type: 'application/zip',
    }),
    env: TEST_AUTH_ENV,
    __store: store,
  });
  assert.equal(createResponse.status, 200);
  const created = await createResponse.json();
  assert.ok(created.storage_key.startsWith(`${PREFIX}user-skills/pending/`));
  assert.equal(created.storage_key.includes('..'), false);

  const completeResponse = await onRequest({
    request: await post({
      operation: 'complete',
      upload_id: created.upload_id,
      storage_key: created.storage_key,
      name: 'My Skill.zip',
    }),
    env: TEST_AUTH_ENV,
    __store: store,
  });
  assert.equal(completeResponse.status, 200);
  const completed = (await completeResponse.json()).upload;
  assert.equal(completed.status, 'pending_review');
  assert.equal(completed.review_available, false);
  assert.ok(completed.storage_key.startsWith(PREFIX));

  const listResponse = await onRequest({
    request: await authenticatedRequest('https://example.com/skill-uploads'),
    env: TEST_AUTH_ENV,
    __store: store,
  });
  assert.equal(listResponse.status, 200);
  assert.equal((await listResponse.json()).uploads.length, 1);
});

test('a user cannot complete a package key from another tenant namespace', async () => {
  const response = await onRequest({
    request: await post({
      operation: 'complete',
      upload_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
      storage_key: 'tenants/floris/users/other/user-skills/pending/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa-stolen.zip',
      name: 'stolen.zip',
    }),
    env: TEST_AUTH_ENV,
    __store: new FakeStore(),
  });
  assert.equal(response.status, 400);
});
