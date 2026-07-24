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

function request(password) {
  return new Request('https://example.com/reset-files', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
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
  });
  assert.equal(response.status, 200);
  const data = await response.json();
  assert.deepEqual(data.deleted, {
    'yuanbao-files': 2,
    'yuanbao-acceptance-shared': 2,
    'yuanbao-auth': 2,
  });
  for (const store of Object.values(stores)) assert.equal(store.keys.length, 0);
});
