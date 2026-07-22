import test from 'node:test';
import assert from 'node:assert/strict';

import { tickUser } from './index.js';

function fakeStore({ duplicate = false, duplicateCode = 'PRECONDITION_FAILED' } = {}) {
  const calls = { set: [], deleted: [] };
  return {
    calls,
    async setJSON(key, value, options) {
      calls.set.push({ key, value, options });
      if (duplicate) {
        const error = new Error(duplicateCode === '412' ? 'Precondition Failed' : 'conditional write failed');
        error.code = duplicateCode;
        throw error;
      }
    },
    async delete(key) { calls.deleted.push(key); },
  };
}

test('scheduled bridge forwards one tick to the proactive Agent', async (t) => {
  const store = fakeStore();
  let forwarded;
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    forwarded = { url: String(url), init };
    return new Response(JSON.stringify({ tick_stats: { notifications_created: 1 } }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  });
  const request = new Request('https://preview.example/proactive-tick?eo_time=1', {
    method: 'POST',
    headers: { 'x-test-schedule': '1' },
  });

  const result = await tickUser(request, store);

  assert.equal(result.status, 200);
  assert.equal(new URL(forwarded.url).pathname, '/proactive');
  assert.equal(new URL(forwarded.url).search, '?eo_time=1');
  assert.equal(JSON.parse(forwarded.init.body).trigger, 'edgeone_schedule');
  assert.equal(forwarded.init.headers.get('makers-conversation-id'), 'yuanbao-proactive-local-user');
  assert.equal(store.calls.set[0].options.onlyIfNew, true);
  assert.deepEqual(store.calls.deleted, []);
});

for (const duplicateCode of ['PRECONDITION_FAILED', '412']) {
  test(`duplicate platform delivery (${duplicateCode}) is a successful no-op`, async (t) => {
    const store = fakeStore({ duplicate: true, duplicateCode });
    const fetchMock = t.mock.method(globalThis, 'fetch', async () => {
      throw new Error('must not be called');
    });
    const result = await tickUser(
      new Request('https://preview.example/proactive-tick', { method: 'POST' }),
      store,
    );
    assert.equal(result.status, 200);
    assert.equal(result.skipped, true);
    assert.equal(fetchMock.mock.callCount(), 0);
  });
}

test('downstream failure releases the Makers Blob claim', async (t) => {
  const store = fakeStore();
  t.mock.method(globalThis, 'fetch', async () => new Response(
    JSON.stringify({ error: 'temporary' }),
    { status: 503, headers: { 'Content-Type': 'application/json' } },
  ));
  const result = await tickUser(
    new Request('https://preview.example/proactive-tick', { method: 'POST' }),
    store,
  );
  assert.equal(result.status, 503);
  assert.equal(result.ok, false);
  assert.equal(store.calls.deleted.length, 1);
  assert.equal(store.calls.deleted[0], store.calls.set[0].key);
});
