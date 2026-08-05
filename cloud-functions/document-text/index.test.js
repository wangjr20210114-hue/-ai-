import test from 'node:test';
import assert from 'node:assert/strict';
import { extractPdfText, onRequest, __test } from './index.js';
import { authenticatedRequest, TEST_AUTH_ENV } from '../../test-utils/auth.js';

const PREFIX = 'tenants/floris/users/11111111-1111-4111-8111-111111111111/';
const FILE_ID = `${PREFIX}uploads/demo/paper.pdf`;

function minimalPdf(text) {
  const stream = `BT /F1 18 Tf 72 120 Td (${text}) Tj ET`;
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',
    `<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`,
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
  ];
  let value = '%PDF-1.4\n';
  const offsets = [0];
  objects.forEach((object, index) => {
    offsets.push(Buffer.byteLength(value));
    value += `${index + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xref = Buffer.byteLength(value);
  value += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  value += offsets.slice(1).map((offset) => `${String(offset).padStart(10, '0')} 00000 n \n`).join('');
  value += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return new TextEncoder().encode(value);
}

test('normalizes PDF.js text items without exposing layout-only gaps', () => {
  assert.equal(__test.normalizedLine([{ str: 'Hello' }, { str: '  world ' }, {}]), 'Hello world');
});

test('the deployed PDF.js adapter extracts selectable text', async () => {
  const result = await extractPdfText(minimalPdf('Hello Floris'));
  assert.match(result.text, /Hello Floris/);
  assert.equal(result.page_count, 1);
  assert.equal(result.truncated, false);
});

test('extracts an owned Makers Blob document through the server adapter', async () => {
  const response = await onRequest({
    request: await authenticatedRequest('https://example.test/document-text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_id: FILE_ID }),
    }),
    env: TEST_AUTH_ENV,
    __store: {
      async getMetadata() { return { contentType: 'application/pdf', size: 64 }; },
      async get() { return new Uint8Array([37, 80, 68, 70]).buffer; },
    },
    async __extractPdfText() {
      return { text: 'paper body', preview: 'paper body', page_count: 2, truncated: false };
    },
  });
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {
    file_id: FILE_ID,
    storage_key: FILE_ID,
    text: 'paper body',
    preview: 'paper body',
    page_count: 2,
    truncated: false,
  });
});

test('rejects a Blob key outside the authenticated tenant', async () => {
  const response = await onRequest({
    request: await authenticatedRequest('https://example.test/document-text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_id: 'tenants/floris/users/other/uploads/paper.pdf' }),
    }),
    env: TEST_AUTH_ENV,
  });
  assert.equal(response.status, 400);
  assert.equal((await response.json()).code, 'INVALID_FILE_ID');
});
