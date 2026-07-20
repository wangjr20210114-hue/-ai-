import test from 'node:test';
import assert from 'node:assert/strict';
import { onRequest, __test } from './index.js';

function mockStore(bytes) {
  return {
    async getMetadata() {
      return { contentType: 'application/pdf', size: bytes.byteLength, headers: { 'content-length': String(bytes.byteLength) } };
    },
    async get() { return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength); },
  };
}

async function call(store, method, suffix = '') {
  return onRequest({
    request: new Request(`https://example.test/files?key=uploads%2Fdemo%2Flarge.pdf${suffix}`, { method }),
    env: {},
    __store: store,
  });
}

test('HEAD exposes the Makers-safe part size without reading the object body', async () => {
  const response = await call(mockStore(new Uint8Array(10)), 'HEAD');
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('content-length'), '10');
  assert.equal(Number(response.headers.get('x-yuanbao-part-size')), __test.DOWNLOAD_PART_BYTES);
});

test('GET part keeps large Blob transfers below the Cloud Function response limit', async () => {
  const bytes = new Uint8Array(__test.DOWNLOAD_PART_BYTES + 3).map((_, index) => index % 251);
  const response = await call(mockStore(bytes), 'GET', '&part=1');
  assert.equal(response.status, 200);
  assert.equal(Number(response.headers.get('content-length')), 3);
  assert.equal(response.headers.get('content-range'), `bytes ${__test.DOWNLOAD_PART_BYTES}-${__test.DOWNLOAD_PART_BYTES + 2}/${bytes.byteLength}`);
  assert.deepEqual(new Uint8Array(await response.arrayBuffer()), bytes.slice(__test.DOWNLOAD_PART_BYTES));
});
