import test from 'node:test';
import assert from 'node:assert/strict';
import { onRequest, __test } from './index.js';
import { authenticatedRequest, TEST_AUTH_ENV } from '../../test-utils/auth.js';

const PREFIX = 'tenants/floris/users/11111111-1111-4111-8111-111111111111/';

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
    request: await authenticatedRequest(
      `https://example.test/files?key=${encodeURIComponent(`${PREFIX}uploads/demo/large.pdf`)}${suffix}`,
      { method },
    ),
    env: TEST_AUTH_ENV,
    __store: store,
  });
}

test('HEAD exposes the Makers-safe part size without reading the object body', async () => {
  const response = await call(mockStore(new Uint8Array(10)), 'HEAD');
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('content-length'), '10');
  assert.equal(response.headers.get('accept-ranges'), null);
  assert.equal(response.headers.get('x-floris-file-size'), '10');
  assert.equal(response.headers.get('x-floris-part-protocol'), 'makers-parts-v1');
  assert.equal(response.headers.get('x-yuanbao-file-size'), '10');
  assert.equal(Number(response.headers.get('x-floris-part-size')), __test.DOWNLOAD_PART_BYTES);
  assert.equal(Number(response.headers.get('x-yuanbao-part-size')), __test.DOWNLOAD_PART_BYTES);
});

test('international Blob filenames remain valid response headers', async () => {
  const value = __test.contentDisposition('uploads/demo/王俊然-毕业论文.pdf', 'document.pdf');
  assert.match(value, /filename="_-_\.pdf"/);
  assert.match(value, /filename\*=UTF-8''%E7%8E%8B/);
  assert.doesNotMatch(value, /王俊然/);
});

test('GET part keeps large Blob transfers below the Cloud Function response limit', async () => {
  const bytes = new Uint8Array(__test.DOWNLOAD_PART_BYTES + 3).map((_, index) => index % 251);
  const response = await call(mockStore(bytes), 'GET', '&part=1');
  assert.equal(response.status, 200);
  assert.equal(Number(response.headers.get('content-length')), 3);
  assert.equal(response.headers.get('content-range'), null);
  assert.equal(response.headers.get('x-floris-part-index'), '1');
  assert.equal(response.headers.get('x-floris-part-start'), String(__test.DOWNLOAD_PART_BYTES));
  assert.equal(response.headers.get('x-floris-part-end'), String(bytes.byteLength));
  assert.deepEqual(new Uint8Array(await response.arrayBuffer()), bytes.slice(__test.DOWNLOAD_PART_BYTES));
});
