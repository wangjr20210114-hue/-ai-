import { getStore } from '@edgeone/pages-blob';

const STORE_NAME = 'yuanbao-acceptance-shared';
const STATE_KEY = 'v2/state.json';
const RESULTS = new Set(['not-run', 'pass', 'fail', 'blocked', 'na']);
const MAX_NOTES = 20_000;
const MAX_AUDIT = 1_500;
const MAX_IMAGE_BYTES = 20 * 1024 * 1024;
const MAX_VIDEO_BYTES = 100 * 1024 * 1024;

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
    },
  });
}

function emptyState() {
  return {
    schemaVersion: 2,
    revision: 0,
    meta: { environment: 'preview', deploymentId: '', tester: '' },
    cases: {},
    audit: [],
    updatedAt: '',
  };
}

function cleanText(value, max = 200) {
  return String(value ?? '').trim().slice(0, max);
}

function safeSegment(value, fallback = 'file') {
  const normalized = String(value || '')
    .normalize('NFKC')
    .replace(/[^\p{L}\p{N}._-]+/gu, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 120);
  return normalized || fallback;
}

function nextTimestamp(previous = '') {
  const parsed = Date.parse(previous);
  const floor = Number.isFinite(parsed) ? parsed + 1 : 0;
  return new Date(Math.max(Date.now(), floor)).toISOString();
}

function validCaseId(value) {
  const id = cleanText(value, 32).toUpperCase();
  return /^[A-Z]+-\d{2}$/.test(id) ? id : '';
}

function clientIdentity(body) {
  return {
    hostId: cleanText(body?.hostId, 100) || 'unknown-host',
    hostName: cleanText(body?.hostName, 120) || '未命名主机',
    tester: cleanText(body?.tester, 120),
  };
}

function writeAllowed(request, env) {
  const expected = cleanText(env?.ACCEPTANCE_WRITE_SECRET, 500);
  if (!expected) return true;
  return cleanText(request.headers.get('x-acceptance-key'), 500) === expected;
}

async function loadState(store) {
  const stored = await store.get(STATE_KEY, { type: 'json', consistency: 'strong' });
  if (!stored || typeof stored !== 'object') return emptyState();
  return {
    ...emptyState(),
    ...stored,
    meta: { ...emptyState().meta, ...(stored.meta || {}) },
    cases: stored.cases && typeof stored.cases === 'object' ? stored.cases : {},
    audit: Array.isArray(stored.audit) ? stored.audit.slice(0, MAX_AUDIT) : [],
  };
}

function auditEntry(caseId, field, before, after, identity, at, extra = {}) {
  return {
    id: crypto.randomUUID(),
    caseId,
    field,
    before,
    after,
    editedAt: at,
    ...identity,
    ...extra,
  };
}

function normalizeRecord(record = {}) {
  return {
    result: RESULTS.has(record.result) ? record.result : 'not-run',
    notes: cleanText(record.notes, MAX_NOTES),
    evidence: Array.isArray(record.evidence) ? record.evidence.slice(0, 50) : [],
    updatedAt: cleanText(record.updatedAt, 50),
    updatedByHostId: cleanText(record.updatedByHostId, 100),
    updatedByHostName: cleanText(record.updatedByHostName, 120),
    updatedByTester: cleanText(record.updatedByTester, 120),
  };
}

async function saveState(store, state) {
  state.revision = Number(state.revision || 0) + 1;
  state.updatedAt = new Date().toISOString();
  state.audit = state.audit.slice(0, MAX_AUDIT);
  await store.setJSON(STATE_KEY, state);
  return state;
}

function conflict(record) {
  return json({
    error: '该用例已被另一台主机更新，请先同步后再保存。',
    code: 'EDIT_CONFLICT',
    record,
  }, 409);
}

async function saveCase(store, body) {
  const caseId = validCaseId(body.caseId);
  if (!caseId) return json({ error: '无效测试用例 ID' }, 400);
  const state = await loadState(store);
  const current = normalizeRecord(state.cases[caseId]);
  const baseUpdatedAt = cleanText(body.baseUpdatedAt, 50);
  if (baseUpdatedAt && current.updatedAt && baseUpdatedAt !== current.updatedAt) return conflict(current);

  const patch = body.patch && typeof body.patch === 'object' ? body.patch : {};
  const next = { ...current };
  if ('result' in patch) {
    if (!RESULTS.has(patch.result)) return json({ error: '无效测试结果' }, 400);
    next.result = patch.result;
  }
  if ('notes' in patch) next.notes = cleanText(patch.notes, MAX_NOTES);

  const identity = clientIdentity(body);
  const at = nextTimestamp(current.updatedAt);
  const changes = [];
  for (const field of ['result', 'notes']) {
    if (current[field] !== next[field]) changes.push(auditEntry(caseId, field, current[field], next[field], identity, at));
  }
  if (!changes.length) return json({ ok: true, state, record: current });

  next.updatedAt = at;
  next.updatedByHostId = identity.hostId;
  next.updatedByHostName = identity.hostName;
  next.updatedByTester = identity.tester;
  state.cases[caseId] = next;
  state.audit.unshift(...changes);
  await saveState(store, state);
  return json({ ok: true, state, record: next });
}

async function saveMeta(store, body) {
  const state = await loadState(store);
  const identity = clientIdentity(body);
  const at = new Date().toISOString();
  const patch = body.meta && typeof body.meta === 'object' ? body.meta : {};
  const next = {
    environment: ['preview', 'local', 'production'].includes(patch.environment) ? patch.environment : state.meta.environment,
    deploymentId: cleanText(patch.deploymentId, 160),
    tester: cleanText(patch.tester, 120),
  };
  const changes = [];
  for (const field of ['environment', 'deploymentId', 'tester']) {
    if (state.meta[field] !== next[field]) changes.push(auditEntry('_RUN_', `meta.${field}`, state.meta[field], next[field], identity, at));
  }
  if (!changes.length) return json({ ok: true, state });
  state.meta = next;
  state.audit.unshift(...changes);
  await saveState(store, state);
  return json({ ok: true, state });
}

async function createUpload(store, body) {
  const caseId = validCaseId(body.caseId);
  if (!caseId) return json({ error: '无效测试用例 ID' }, 400);
  const name = cleanText(body.name, 240) || 'evidence';
  const contentType = cleanText(body.contentType, 120).toLowerCase();
  const size = Number(body.size || 0);
  const isImage = contentType.startsWith('image/');
  const isVideo = contentType.startsWith('video/');
  const limit = isImage ? MAX_IMAGE_BYTES : isVideo ? MAX_VIDEO_BYTES : 0;
  if (!limit) return json({ error: '证据只允许图片或视频' }, 400);
  if (!Number.isFinite(size) || size <= 0 || size > limit) {
    return json({ error: `${isImage ? '图片' : '视频'}大小必须在 1B 到 ${limit / 1024 / 1024}MB 之间` }, 400);
  }
  const key = `v2/evidence/${caseId}/${crypto.randomUUID()}-${safeSegment(name, isImage ? 'image' : 'video')}`;
  const upload = await store.createUploadUrl(key, { expireSeconds: 600, contentType });
  return json({
    ...upload,
    evidence: {
      id: crypto.randomUUID(),
      key,
      name,
      contentType,
      size,
      kind: isImage ? 'image' : 'video',
      contentUrl: `/acceptance?evidence=${encodeURIComponent(key)}`,
    },
  });
}

async function attachEvidence(store, body) {
  const caseId = validCaseId(body.caseId);
  const evidence = body.evidence && typeof body.evidence === 'object' ? body.evidence : {};
  const key = cleanText(evidence.key, 500);
  if (!caseId || !key.startsWith(`v2/evidence/${caseId}/`)) return json({ error: '无效证据标识' }, 400);
  const metadata = await store.getMetadata(key);
  if (!metadata) return json({ error: '证据文件尚未上传完成' }, 400);

  const state = await loadState(store);
  const current = normalizeRecord(state.cases[caseId]);
  const identity = clientIdentity(body);
  const at = new Date().toISOString();
  const item = {
    id: cleanText(evidence.id, 100) || crypto.randomUUID(),
    key,
    name: cleanText(evidence.name, 240) || '证据文件',
    contentType: cleanText(evidence.contentType, 120) || metadata.contentType || 'application/octet-stream',
    size: Number(evidence.size || metadata.size || 0),
    kind: evidence.kind === 'video' ? 'video' : 'image',
    contentUrl: `/acceptance?evidence=${encodeURIComponent(key)}`,
    uploadedAt: at,
    uploadedByHostId: identity.hostId,
    uploadedByHostName: identity.hostName,
    uploadedByTester: identity.tester,
  };
  if (current.evidence.some(existing => existing.key === key)) return json({ ok: true, state, record: current });
  current.evidence = [item, ...current.evidence].slice(0, 50);
  current.updatedAt = at;
  current.updatedByHostId = identity.hostId;
  current.updatedByHostName = identity.hostName;
  current.updatedByTester = identity.tester;
  state.cases[caseId] = current;
  state.audit.unshift(auditEntry(caseId, 'evidence.add', '', item.name, identity, at, { evidenceId: item.id }));
  await saveState(store, state);
  return json({ ok: true, state, record: current });
}

async function removeEvidence(store, body) {
  const caseId = validCaseId(body.caseId);
  const evidenceId = cleanText(body.evidenceId, 100);
  if (!caseId || !evidenceId) return json({ error: '无效删除参数' }, 400);
  const state = await loadState(store);
  const current = normalizeRecord(state.cases[caseId]);
  const item = current.evidence.find(value => value.id === evidenceId);
  if (!item) return json({ error: '证据不存在' }, 404);
  if (!cleanText(item.key, 500).startsWith(`v2/evidence/${caseId}/`)) return json({ error: '无效证据标识' }, 400);
  await store.delete(item.key);
  current.evidence = current.evidence.filter(value => value.id !== evidenceId);
  const identity = clientIdentity(body);
  const at = new Date().toISOString();
  current.updatedAt = at;
  current.updatedByHostId = identity.hostId;
  current.updatedByHostName = identity.hostName;
  current.updatedByTester = identity.tester;
  state.cases[caseId] = current;
  state.audit.unshift(auditEntry(caseId, 'evidence.remove', item.name, '', identity, at, { evidenceId }));
  await saveState(store, state);
  return json({ ok: true, state, record: current });
}

async function importResults(store, body) {
  const payload = body.payload && typeof body.payload === 'object' ? body.payload : {};
  if (!Array.isArray(payload.cases)) return json({ error: '导入文件缺少 cases 数组' }, 400);
  const state = await loadState(store);
  const identity = clientIdentity(body);
  const at = new Date().toISOString();
  let imported = 0;
  for (const raw of payload.cases.slice(0, 500)) {
    const caseId = validCaseId(raw.id);
    if (!caseId) continue;
    const current = normalizeRecord(state.cases[caseId]);
    const nextResult = RESULTS.has(raw.result) ? raw.result : current.result;
    const nextNotes = 'notes' in raw ? cleanText(raw.notes, MAX_NOTES) : current.notes;
    const changes = [];
    if (current.result !== nextResult) changes.push(auditEntry(caseId, 'result', current.result, nextResult, identity, at, { source: 'import' }));
    if (current.notes !== nextNotes) changes.push(auditEntry(caseId, 'notes', current.notes, nextNotes, identity, at, { source: 'import' }));
    if (!changes.length) continue;
    state.cases[caseId] = {
      ...current,
      result: nextResult,
      notes: nextNotes,
      updatedAt: at,
      updatedByHostId: identity.hostId,
      updatedByHostName: identity.hostName,
      updatedByTester: identity.tester,
    };
    state.audit.unshift(...changes);
    imported += 1;
  }
  if (payload.environment || payload.deploymentId || payload.tester) {
    state.meta = {
      environment: ['preview', 'local', 'production'].includes(payload.environment) ? payload.environment : state.meta.environment,
      deploymentId: cleanText(payload.deploymentId, 160),
      tester: cleanText(payload.tester, 120),
    };
  }
  if (imported) await saveState(store, state);
  return json({ ok: true, imported, state });
}

async function getEvidence(store, request) {
  const key = cleanText(new URL(request.url).searchParams.get('evidence'), 500);
  if (!key.startsWith('v2/evidence/')) return json({ error: '无效证据标识' }, 400);
  const [body, metadata] = await Promise.all([
    store.get(key, { type: 'arrayBuffer', consistency: 'strong' }),
    store.getMetadata(key),
  ]);
  if (!body) return json({ error: '证据不存在' }, 404);
  return new Response(body, {
    headers: {
      'Content-Type': metadata?.contentType || 'application/octet-stream',
      'Content-Disposition': `inline; filename="${safeSegment(key.split('/').pop(), 'evidence')}"`,
      'Cache-Control': 'private, max-age=300',
      'X-Content-Type-Options': 'nosniff',
    },
  });
}

export async function onRequest(context) {
  const { request, env = {} } = context;
  const store = context.__store || getStore({ name: STORE_NAME, consistency: 'strong' });
  try {
    if (request.method === 'GET') {
      if (new URL(request.url).searchParams.has('evidence')) return await getEvidence(store, request);
      const state = await loadState(store);
      return json({ ...state, writeProtected: Boolean(env.ACCEPTANCE_WRITE_SECRET) });
    }
    if (request.method !== 'POST') return json({ error: 'Method not allowed' }, 405);
    if (!writeAllowed(request, env)) return json({ error: '同步密钥错误' }, 403);
    const body = await request.json();
    if (body.operation === 'saveCase') return await saveCase(store, body);
    if (body.operation === 'saveMeta') return await saveMeta(store, body);
    if (body.operation === 'createUpload') return await createUpload(store, body);
    if (body.operation === 'attachEvidence') return await attachEvidence(store, body);
    if (body.operation === 'removeEvidence') return await removeEvidence(store, body);
    if (body.operation === 'import') return await importResults(store, body);
    return json({ error: '未知操作' }, 400);
  } catch (error) {
    console.error('acceptance_api_error', { message: error?.message, stack: error?.stack });
    return json({ error: '验收数据服务暂时不可用，请稍后重试。' }, 500);
  }
}

export const __test = { emptyState, normalizeRecord, validCaseId, safeSegment, clientIdentity, nextTimestamp };
