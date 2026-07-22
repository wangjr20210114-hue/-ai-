import test from 'node:test';
import assert from 'node:assert/strict';
import { onRequest, __test } from './index.js';

function mockStore() {
  const values = new Map();
  const metadata = new Map();
  return {
    values,
    metadata,
    async get(key, options = {}) {
      if (!values.has(key)) return null;
      const value = values.get(key);
      if (options.type === 'json') return structuredClone(value);
      return value;
    },
    async setJSON(key, value) { values.set(key, structuredClone(value)); },
    async getMetadata(key) { return metadata.get(key) || null; },
    async createUploadUrl(key) { return { url: `https://upload.example/${key}`, key, expiresAt: 123 }; },
    async delete(key) { values.delete(key); metadata.delete(key); },
  };
}

async function call(store, body, headers = {}) {
  const request = new Request('https://example.test/acceptance', {
    method: body ? 'POST' : 'GET',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: body ? JSON.stringify(body) : undefined,
  });
  return onRequest({ request, env: {}, __store: store });
}

test('validation helpers normalize records and reject unsafe case ids', () => {
  assert.equal(__test.validCaseId('core-01'), 'CORE-01');
  assert.equal(__test.validCaseId('../bad'), '');
  assert.equal(__test.normalizeRecord({ result: 'unknown', notes: ' a ' }).result, 'not-run');
  assert.equal(__test.safeSegment('../../截图 1.png'), '..-..-截图-1.png');
});

test('saveCase persists shared state and audit identity', async () => {
  const store = mockStore();
  const response = await call(store, {
    operation: 'saveCase', caseId: 'CORE-03', patch: { result: 'fail', notes: '代码块溢出' },
    hostId: 'host-a', hostName: 'MacBook-A', tester: '王',
  });
  assert.equal(response.status, 200);
  const payload = await response.json();
  assert.equal(payload.record.result, 'fail');
  assert.equal(payload.record.updatedByHostName, 'MacBook-A');
  assert.equal(payload.state.audit.length, 2);
  assert.deepEqual(payload.state.audit.map(item => item.field), ['result', 'notes']);
});

test('saveCase uses simple last-write-wins across hosts', async () => {
  const store = mockStore();
  const first = await call(store, {
    operation: 'saveCase', caseId: 'CORE-01', patch: { result: 'pass' }, hostId: 'a', hostName: 'A',
  });
  const saved = await first.json();
  await call(store, {
    operation: 'saveCase', caseId: 'CORE-01', patch: { notes: 'newer' }, baseUpdatedAt: saved.record.updatedAt,
    hostId: 'b', hostName: 'B',
  });
  const latest = await call(store, {
    operation: 'saveCase', caseId: 'CORE-01', patch: { notes: 'stale' }, baseUpdatedAt: saved.record.updatedAt,
    hostId: 'a', hostName: 'A',
  });
  assert.equal(latest.status, 200);
  const payload = await latest.json();
  assert.equal(payload.record.notes, 'stale');
  assert.equal(payload.record.updatedByHostName, 'A');
});

test('schema v1 result export imports into v2 state', async () => {
  const store = mockStore();
  const response = await call(store, {
    operation: 'import', hostId: 'host-import', hostName: '导入主机', tester: 'Tester',
    payload: {
      schemaVersion: 1, environment: 'preview', deploymentId: 'dptest',
      cases: [
        { id: 'CORE-03', result: 'fail', notes: 'markdown 溢出' },
        { id: 'CORE-05', result: 'fail', notes: '无停止按钮' },
      ],
    },
  });
  const payload = await response.json();
  assert.equal(payload.imported, 2);
  assert.equal(payload.state.cases['CORE-05'].notes, '无停止按钮');
  assert.equal(payload.state.meta.deploymentId, 'dptest');
});

test('evidence uses presigned upload and is attached only after blob exists', async () => {
  const store = mockStore();
  const signed = await call(store, {
    operation: 'createUpload', caseId: 'READ-01', name: 'screen.png', contentType: 'image/png', size: 1024,
  });
  const upload = await signed.json();
  assert.match(upload.url, /^https:\/\/upload\.example\//);
  store.metadata.set(upload.evidence.key, { contentType: 'image/png', size: 1024 });
  const attached = await call(store, {
    operation: 'attachEvidence', caseId: 'READ-01', evidence: upload.evidence,
    hostId: 'host-a', hostName: 'A', tester: 'Tester',
  });
  const payload = await attached.json();
  assert.equal(payload.record.evidence.length, 1);
  assert.equal(payload.record.evidence[0].uploadedByHostName, 'A');
});
