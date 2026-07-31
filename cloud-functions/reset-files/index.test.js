import test from 'node:test';
import assert from 'node:assert/strict';

import { onRequest, __test } from './index.js';
import { authenticatedRequest, TEST_AUTH_ENV } from '../../test-utils/auth.js';

const PREFIX = 'tenants/floris/users/11111111-1111-4111-8111-111111111111/';

class FakeStore {
  constructor(keys = []) {
    this.keys = [...keys];
  }

  async list({ prefix = '' } = {}) {
    return { blobs: this.keys.filter((key) => key.startsWith(prefix)).map((key) => ({ key })) };
  }

  async delete(key) {
    this.keys = this.keys.filter((item) => item !== key);
  }
}

class FakeConversationStore {
  constructor(ids = []) {
    this.ids = [...ids];
  }

  async listConversations({ after } = {}) {
    if (after) return { items: [], nextCursor: undefined };
    return {
      items: this.ids.slice(0, 100).map((conversationId) => ({ conversationId })),
      nextCursor: this.ids.length > 100 ? 'next-page' : undefined,
    };
  }

  async deleteConversation({ conversationId }) {
    this.ids = this.ids.filter((item) => item !== conversationId);
  }
}

function request(confirmation, operation = 'clear') {
  return authenticatedRequest('https://example.com/reset-files', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ confirmation, operation }),
  });
}

test('wrong confirmation leaves the Makers Blob store untouched', async () => {
  const stores = Object.fromEntries(__test.STORE_NAMES.map((name) => [name, new FakeStore([`${PREFIX}${name}/test`])]));
  const response = await onRequest({
    request: await request('wrong'),
    env: TEST_AUTH_ENV,
    __stores: stores,
    __conversationStore: new FakeConversationStore(['yb7_keep']),
  });
  assert.equal(response.status, 403);
  for (const store of Object.values(stores)) assert.equal(store.keys.length, 1);
});

test('valid confirmation clears only this user files and conversations', async () => {
  const stores = Object.fromEntries(__test.STORE_NAMES.map((name) => [name, new FakeStore([
    `${PREFIX}${name}/one`,
    `${PREFIX}${name}/two`,
    `tenants/floris/users/22222222-2222-4222-8222-222222222222/${name}/keep`,
  ])]));
  const response = await onRequest({
    request: await request('DELETE'),
    env: TEST_AUTH_ENV,
    __stores: stores,
    __conversationStore: new FakeConversationStore(['yb7_one', 'yb7_two']),
  });
  assert.equal(response.status, 200);
  const data = await response.json();
  assert.equal(data.conversations_deleted, 2);
  assert.deepEqual(data.deleted, {
    'yuanbao-files': 2,
  });
  for (const store of Object.values(stores)) {
    assert.deepEqual(store.keys, [
      `tenants/floris/users/22222222-2222-4222-8222-222222222222/yuanbao-files/keep`,
    ]);
  }
});

test('inspect returns conversation ids without deleting any Makers data', async () => {
  const conversations = new FakeConversationStore(['yb7_one', 'yb7_two']);
  const stores = Object.fromEntries(__test.STORE_NAMES.map((name) => [name, new FakeStore([`${PREFIX}${name}/one`])]));
  const response = await onRequest({
    request: await request('DELETE', 'inspect'),
    env: TEST_AUTH_ENV,
    __stores: stores,
    __conversationStore: conversations,
  });
  assert.equal(response.status, 200);
  assert.deepEqual((await response.json()).conversation_ids, ['yb7_one', 'yb7_two']);
  assert.deepEqual(conversations.ids, ['yb7_one', 'yb7_two']);
  for (const store of Object.values(stores)) assert.equal(store.keys.length, 1);
});
