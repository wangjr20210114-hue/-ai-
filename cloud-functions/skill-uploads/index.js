import { getStore } from '@edgeone/pages-blob';
import { currentUser, tenantPrefix } from '../../auth/current-user.js';
import { publicEntitlements } from '../../auth/entitlements.js';

const STORE_NAME = 'yuanbao-files';
const MAX_PACKAGE_BYTES = 2 * 1024 * 1024;
const MAX_DECLARATIVE_SKILL_CHARS = 12_000;
const MAX_REMOTE_SKILL_BYTES = 64 * 1024;
const PUBLIC_SKILL_HOSTS = new Set([
  'github.com',
  'gitlab.com',
  'raw.githubusercontent.com',
]);

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

function importError(code, status = 400) {
  const error = new Error(code);
  error.code = code;
  error.status = status;
  return error;
}

function fallbackSkillName(value) {
  return String(value || '')
    .split(/[\\/]/).pop()
    ?.replace(/\.(floris-skill\.)?(md|json)$/i, '')
    .replace(/[-_]+/g, ' ')
    .trim()
    .slice(0, 80) || 'Private Skill';
}

function publicSkillMarkdownUrl(value) {
  let url;
  try { url = new URL(String(value || '').trim()); } catch {
    throw importError('SKILL_SOURCE_INVALID');
  }
  if (url.protocol !== 'https:' || !PUBLIC_SKILL_HOSTS.has(url.hostname)) {
    throw importError('SKILL_SOURCE_INVALID');
  }
  if (url.username || url.password || url.port) {
    throw importError('SKILL_SOURCE_INVALID');
  }
  if (url.hostname === 'raw.githubusercontent.com') return url.toString();
  const parts = url.pathname.split('/').filter(Boolean);
  if (url.hostname === 'github.com') {
    if (parts.length < 2) throw importError('SKILL_SOURCE_INVALID');
    const [owner, repo] = parts;
    if (parts[2] === 'blob' && parts.length >= 5) {
      return `https://raw.githubusercontent.com/${owner}/${repo}/${parts[3]}/${parts.slice(4).join('/')}`;
    }
    if (parts[2] === 'tree' && parts.length >= 4) {
      return `https://raw.githubusercontent.com/${owner}/${repo}/${parts[3]}/${parts.slice(4).concat('SKILL.md').join('/')}`;
    }
    return `https://raw.githubusercontent.com/${owner}/${repo}/HEAD/SKILL.md`;
  }
  const marker = parts.indexOf('-');
  if (marker >= 2 && parts[marker + 1] === 'raw') return url.toString();
  if (parts.length < 2) throw importError('SKILL_SOURCE_INVALID');
  return `https://gitlab.com/${parts[0]}/${parts[1]}/-/raw/HEAD/SKILL.md`;
}

function skillTextMetadata(text) {
  const match = text.match(/^---\s*\n([\s\S]*?)\n---(?:\s*\n|$)/);
  if (!match) return {};
  return Object.fromEntries(match[1].split(/\r?\n/).flatMap((line) => {
    const field = line.match(/^([a-zA-Z][\w-]*):\s*(.+)$/);
    return field
      ? [[field[1].toLowerCase(), field[2].trim().replace(/^['"]|['"]$/g, '')]]
      : [];
  }));
}

async function boundedResponseText(response) {
  const declaredSize = Number(response.headers.get('content-length') || 0);
  if (declaredSize > MAX_REMOTE_SKILL_BYTES) {
    throw importError('SKILL_SOURCE_TOO_LARGE', 413);
  }
  if (!response.body?.getReader) {
    const value = await response.text();
    if (new TextEncoder().encode(value).byteLength > MAX_REMOTE_SKILL_BYTES) {
      throw importError('SKILL_SOURCE_TOO_LARGE', 413);
    }
    return value;
  }
  const reader = response.body.getReader();
  const chunks = [];
  let size = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_REMOTE_SKILL_BYTES) {
      await reader.cancel().catch(() => {});
      throw importError('SKILL_SOURCE_TOO_LARGE', 413);
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  try { return new TextDecoder('utf-8', { fatal: true }).decode(bytes); } catch {
    throw importError('SKILL_SOURCE_ENCODING_INVALID', 422);
  }
}

async function resolvePublicSkill(value, fetcher = fetch) {
  const sourceUrl = String(value || '').trim().slice(0, 1000);
  const markdownUrl = publicSkillMarkdownUrl(sourceUrl);
  let response;
  try {
    response = await fetcher(markdownUrl, {
      headers: { Accept: 'text/markdown,text/plain;q=0.9' },
      redirect: 'error',
    });
  } catch {
    throw importError('SKILL_SOURCE_FETCH_FAILED', 502);
  }
  if (!response.ok) throw importError('SKILL_SOURCE_FETCH_FAILED', 502);
  const instructions = (await boundedResponseText(response)).trim();
  if (!instructions) throw importError('SKILL_SOURCE_EMPTY', 422);
  if (instructions.length > MAX_DECLARATIVE_SKILL_CHARS) {
    throw importError('SKILL_SOURCE_TOO_LARGE', 413);
  }
  const metadata = skillTextMetadata(instructions);
  return {
    name: String(metadata.name || fallbackSkillName(new URL(sourceUrl).pathname)).trim().slice(0, 80),
    description: String(metadata.description || '').trim().slice(0, 280),
    instructions,
    source_type: 'url',
    source_url: sourceUrl,
  };
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
    return json({ error: '请先登录后管理私有 Skill', code: 'LOGIN_REQUIRED' }, 403);
  }
  const prefix = tenantPrefix(user);
  const store = context.__store || getStore({ name: STORE_NAME, consistency: 'strong' });

  if (request.method === 'GET') {
    return json({ uploads: await records(store, prefix) });
  }
  if (request.method !== 'POST') return json({ error: 'Method not allowed' }, 405);
  const body = await request.json().catch(() => ({}));
  const operation = String(body.operation || 'create');

  if (operation === 'resolve_url') {
    try {
      return json({
        skill: await resolvePublicSkill(body.source_url, context.__fetch || fetch),
      });
    } catch (error) {
      const code = String(error?.code || 'SKILL_SOURCE_FETCH_FAILED');
      return json({ error: code, code }, Number(error?.status || 502));
    }
  }

  const limit = Number(publicEntitlements(user).limits.userSkillUploads || 0);
  const existing = await records(store, prefix);

  if (operation === 'publish_declarative') {
    const sourceSkillId = String(body.source_skill_id || '').trim();
    const instructions = String(body.instructions || '').trim();
    if (!/^user-[a-z0-9-]{8,80}$/.test(sourceSkillId) || !instructions) {
      return json({ error: '无效的声明式 Skill', code: 'INVALID_SKILL' }, 400);
    }
    if (instructions.length > MAX_DECLARATIVE_SKILL_CHARS) {
      return json({ error: 'Skill 说明不能超过 12000 字符', code: 'SKILL_TOO_LARGE' }, 400);
    }
    if (
      !existing.some((item) => item.id === sourceSkillId)
      && existing.length >= limit
    ) {
      return json({ error: '已达到当前会员等级的 Skill 数量上限', code: 'UPLOAD_LIMIT' }, 403);
    }
    const record = {
      id: sourceSkillId,
      source_skill_id: sourceSkillId,
      name: safeName(body.name || 'Private Skill'),
      description: String(body.description || '').trim().slice(0, 280),
      instructions,
      storage_key: '',
      status: 'stored',
      visibility: 'private',
      review_status: 'pending_review',
      review_available: true,
      source_type: 'declarative',
      size: new TextEncoder().encode(instructions).byteLength,
      installed_at: Number(body.installed_at || Date.now()),
      review_requested_at: Date.now(),
    };
    await store.setJSON(`${prefix}user-skills/records/${sourceSkillId}.json`, record);
    return json({ upload: record });
  }

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
    const storageKey = `${prefix}user-skills/private/${uploadId}-${name}`;
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
      || !storageKey.startsWith(`${prefix}user-skills/private/${uploadId}-`)
    ) {
      return json({ error: '无效 Skill 上传标识' }, 400);
    }
    const metadata = await store.getMetadata(storageKey);
    if (!metadata) return json({ error: 'Skill 包尚未上传完成' }, 409);
    const record = {
      id: uploadId,
      name: safeName(body.name),
      storage_key: storageKey,
      status: 'stored',
      visibility: 'private',
      review_status: 'not_submitted',
      review_available: true,
      source_type: 'zip',
      size: Number(metadata.size || 0),
      installed_at: Date.now(),
    };
    await store.setJSON(`${prefix}user-skills/records/${uploadId}.json`, record);
    return json({ upload: record });
  }
  if (operation === 'publish') {
    const uploadId = String(body.upload_id || '');
    const record = existing.find((item) => String(item.id || '') === uploadId);
    if (
      !record
      || !String(record.storage_key || '').startsWith(`${prefix}user-skills/`)
    ) {
      return json({ error: '私有 Skill 包不存在', code: 'SKILL_NOT_FOUND' }, 404);
    }
    const updated = {
      ...record,
      visibility: 'private',
      review_status: 'pending_review',
      review_available: true,
      review_requested_at: Date.now(),
    };
    await store.setJSON(`${prefix}user-skills/records/${uploadId}.json`, updated);
    return json({ upload: updated });
  }
  return json({ error: 'Unsupported operation' }, 400);
}

export const __test = {
  MAX_DECLARATIVE_SKILL_CHARS,
  MAX_PACKAGE_BYTES,
  MAX_REMOTE_SKILL_BYTES,
  publicSkillMarkdownUrl,
  resolvePublicSkill,
  safeName,
};
