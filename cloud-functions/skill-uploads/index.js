import { getStore } from '@edgeone/pages-blob';
import { currentUser, tenantPrefix } from '../../auth/current-user.js';
import { publicEntitlements } from '../../auth/entitlements.js';

const STORE_NAME = 'yuanbao-files';
const MAX_PACKAGE_BYTES = 2 * 1024 * 1024;

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
    },
  });
}

function safeName(value) {
  return String(value || 'skill-package.zip')
    .normalize('NFKC')
    .replace(/[^\p{L}\p{N}._-]+/gu, '-')
    .replace(/\.{2,}/g, '.')
    .replace(/^[.-]+|[.-]+$/g, '')
    .slice(0, 120) || 'skill-package.zip';
}

async function records(store, prefix) {
  const { blobs = [] } = await store.list({
    prefix: `${prefix}user-skills/records/`,
    consistency: 'strong',
  });
  const values = await Promise.all(
    blobs.slice(0, 100).map((item) => store.get(item.key, {
      type: 'json',
      consistency: 'strong',
    })),
  );
  return values.filter((item) => item && typeof item === 'object');
}

export async function onRequest(context) {
  const { request, env = {} } = context;
  let user;
  try { user = await currentUser(request, env); } catch { return json({ error: 'Unauthorized' }, 401); }
  if (user.auth_type === 'guest') {
    return json({ error: '请先登录微信后上传 Skill', code: 'LOGIN_REQUIRED' }, 403);
  }
  const prefix = tenantPrefix(user);
  const store = context.__store || getStore({ name: STORE_NAME, consistency: 'strong' });

  if (request.method === 'GET') {
    return json({ uploads: await records(store, prefix) });
  }
  if (request.method !== 'POST') return json({ error: 'Method not allowed' }, 405);
  const body = await request.json().catch(() => ({}));
  const operation = String(body.operation || 'create');
  const limit = Number(publicEntitlements(user).limits.userSkillUploads || 0);
  const existing = await records(store, prefix);

  if (operation === 'create') {
    if (existing.length >= limit) {
      return json({ error: '已达到当前会员等级的 Skill 上传数量上限', code: 'UPLOAD_LIMIT' }, 403);
    }
    const name = safeName(body.name);
    const contentType = String(body.content_type || '');
    const size = Number(body.size || 0);
    if (!name.toLowerCase().endsWith('.zip') || ![
      'application/zip',
      'application/x-zip-compressed',
    ].includes(contentType)) {
      return json({ error: 'Skill 包必须是 ZIP 文件' }, 400);
    }
    if (!Number.isFinite(size) || size <= 0 || size > MAX_PACKAGE_BYTES) {
      return json({ error: 'Skill 包大小必须在 1B 到 2MB 之间' }, 400);
    }
    const uploadId = crypto.randomUUID();
    const storageKey = `${prefix}user-skills/pending/${uploadId}-${name}`;
    const upload = await store.createUploadUrl(storageKey, {
      expireSeconds: 600,
      contentType,
    });
    return json({
      upload_id: uploadId,
      storage_key: storageKey,
      ...upload,
    });
  }

  if (operation === 'complete') {
    const uploadId = String(body.upload_id || '');
    const storageKey = String(body.storage_key || '');
    if (
      !/^[0-9a-f-]{36}$/i.test(uploadId)
      || !storageKey.startsWith(`${prefix}user-skills/pending/${uploadId}-`)
    ) {
      return json({ error: '无效 Skill 上传标识' }, 400);
    }
    const metadata = await store.getMetadata(storageKey);
    if (!metadata) return json({ error: 'Skill 包尚未上传完成' }, 409);
    const record = {
      id: uploadId,
      name: safeName(body.name),
      storage_key: storageKey,
      status: 'pending_review',
      review_available: false,
      size: Number(metadata.size || 0),
      submitted_at: Date.now(),
    };
    await store.setJSON(`${prefix}user-skills/records/${uploadId}.json`, record);
    return json({ upload: record });
  }
  return json({ error: 'Unsupported operation' }, 400);
}

export const __test = { MAX_PACKAGE_BYTES, safeName };
