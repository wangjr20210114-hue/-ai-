import test from 'node:test';
import assert from 'node:assert/strict';

import { onRequest, __test } from './index.js';

class FakeStore {
  constructor(keys = []) {
    this.keys = [...keys];
  }

  async list() {
    return { blobs: this.keys.map((key) => ({ key })) };
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

function request(password, operation = 'clear') {
  return new Request('https://example.com/reset-files', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password, operation }),
  });
}

test('password comparison does not accept empty or partial values', () => {
  assert.equal(__test.secureEqual('', 'secret'), false);
  assert.equal(__test.secureEqual('sec', 'secret'), false);
  assert.equal(__test.secureEqual('secret', 'secret'), true);
});

test('wrong password leaves every Makers Blob store untouched', async () => {
  const stores = Object.fromEntries(__test.STORE_NAMES.map((name) => [name, new FakeStore([`${name}/test`])]));
  const response = await onRequest({
    request: request('wrong'),
    env: { DATA_CLEAR_PASSWORD: 'secret' },
    __stores: stores,
    __conversationStore: new FakeConversationStore(['yb7_keep']),
  });
  assert.equal(response.status, 403);
  for (const store of Object.values(stores)) assert.equal(store.keys.length, 1);
});

test('valid password clears files, acceptance records and scheduler claims', async () => {
  const stores = Object.fromEntries(__test.STORE_NAMES.map((name) => [name, new FakeStore([
    `${name}/one`,
    `${name}/two`,
  ])]));
  const response = await onRequest({
    request: request('secret'),
    env: { DATA_CLEAR_PASSWORD: 'secret' },
    __stores: stores,
    __conversationStore: new FakeConversationStore(['yb7_one', 'yb7_two']),
  });
  assert.equal(response.status, 200);
  const data = await response.json();
  assert.equal(data.conversations_deleted, 2);
  assert.deepEqual(data.deleted, {
    'yuanbao-files': 2,
    'yuanbao-acceptance-shared': 2,
    'yuanbao-auth': 2,
  });
  for (const store of Object.values(stores)) assert.equal(store.keys.length, 0);
});

test('inspect returns conversation ids without deleting any Makers data', async () => {
  const conversations = new FakeConversationStore(['yb7_one', 'yb7_two']);
  const stores = Object.fromEntries(__test.STORE_NAMES.map((name) => [name, new FakeStore([`${name}/one`])]));
  const response = await onRequest({
    request: request('secret', 'inspect'),
    env: { DATA_CLEAR_PASSWORD: 'secret' },
    __stores: stores,
    __conversationStore: conversations,
  });
  assert.equal(response.status, 200);
  assert.deepEqual((await response.json()).conversation_ids, ['yb7_one', 'yb7_two']);
  assert.deepEqual(conversations.ids, ['yb7_one', 'yb7_two']);
  for (const store of Object.values(stores)) assert.equal(store.keys.length, 1);
});
