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

test('presigned ZIP remains private until its owner requests marketplace review', async () => {
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
  assert.ok(created.storage_key.startsWith(`${PREFIX}user-skills/private/`));
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
  assert.equal(completed.status, 'stored');
  assert.equal(completed.visibility, 'private');
  assert.equal(completed.review_status, 'not_submitted');
  assert.equal(completed.review_available, true);
  assert.ok(completed.storage_key.startsWith(PREFIX));

  const publishResponse = await onRequest({
    request: await post({
      operation: 'publish',
      upload_id: completed.id,
    }),
    env: TEST_AUTH_ENV,
    __store: store,
  });
  assert.equal(publishResponse.status, 200);
  const published = (await publishResponse.json()).upload;
  assert.equal(published.visibility, 'private');
  assert.equal(published.review_status, 'pending_review');
  assert.ok(published.review_requested_at > 0);

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
      storage_key: 'tenants/floris/users/other/user-skills/private/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa-stolen.zip',
      name: 'stolen.zip',
    }),
    env: TEST_AUTH_ENV,
    __store: new FakeStore(),
  });
  assert.equal(response.status, 400);
});

test('declarative Skill enters review only after an explicit marketplace request', async () => {
  const store = new FakeStore();
  const response = await onRequest({
    request: await post({
      operation: 'publish_declarative',
      source_skill_id: 'user-writer-1234567890',
      name: 'Writer',
      description: 'Short answers',
      instructions: 'Use concise paragraphs.',
      installed_at: 1234,
    }),
    env: TEST_AUTH_ENV,
    __store: store,
  });
  assert.equal(response.status, 200);
  const record = (await response.json()).upload;
  assert.equal(record.source_type, 'declarative');
  assert.equal(record.visibility, 'private');
  assert.equal(record.review_status, 'pending_review');
  assert.equal(record.source_skill_id, 'user-writer-1234567890');
});

test('repository Skill import is resolved by the authenticated backend boundary', async () => {
  let requestedUrl = '';
  const response = await onRequest({
    request: await post({
      operation: 'resolve_url',
      source_url: 'https://github.com/acme/research-skill',
    }),
    env: TEST_AUTH_ENV,
    __store: new FakeStore(),
    __fetch: async (url) => {
      requestedUrl = String(url);
      return new Response(
        '---\nname: Research helper\ndescription: Use primary papers\n---\nPrefer primary sources.',
        { headers: { 'Content-Type': 'text/markdown' } },
      );
    },
  });
  assert.equal(response.status, 200);
  assert.equal(
    requestedUrl,
    'https://raw.githubusercontent.com/acme/research-skill/HEAD/SKILL.md',
  );
  const skill = (await response.json()).skill;
  assert.equal(skill.name, 'Research helper');
  assert.equal(skill.description, 'Use primary papers');
  assert.equal(skill.source_type, 'url');
  assert.equal(skill.source_url, 'https://github.com/acme/research-skill');
});

test('repository Skill import rejects non-allowlisted network targets before fetch', async () => {
  let fetched = false;
  const response = await onRequest({
    request: await post({
      operation: 'resolve_url',
      source_url: 'https://internal.example.test/SKILL.md',
    }),
    env: TEST_AUTH_ENV,
    __store: new FakeStore(),
    __fetch: async () => {
      fetched = true;
      return new Response('unexpected');
    },
  });
  assert.equal(response.status, 400);
  assert.equal((await response.json()).code, 'SKILL_SOURCE_INVALID');
  assert.equal(fetched, false);
});
