import { getStore } from '@edgeone/pages-blob';
import { currentUser, tenantPrefix } from '../../auth/current-user.js';

const MAX_FILE_BYTES = 20 * 1024 * 1024;

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
}

function safeSegment(value, fallback) {
  const normalized = String(value || '')
    .normalize('NFKC')
    .replace(/[^\p{L}\p{N}._-]+/gu, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 100);
  return normalized || fallback;
}

export async function onRequest(context) {
  const { request, env } = context;
  let user;
  try { user = await currentUser(request, env); } catch { return json({ error: 'Unauthorized' }, 401); }
  const prefix = tenantPrefix(user, env);
  const store = getStore({ name: 'yuanbao-files', consistency: 'strong' });

  if (request.method === 'POST') {
    const body = await request.json();
    const name = String(body.name || 'document.pdf');
    const contentType = String(body.content_type || 'application/pdf');
    const size = Number(body.size || 0);
    if (contentType !== 'application/pdf' || !name.toLowerCase().endsWith('.pdf')) {
      return json({ error: '仅支持 PDF 文件' }, 400);
    }
    if (!Number.isFinite(size) || size <= 0 || size > MAX_FILE_BYTES) {
      return json({ error: 'PDF 大小必须在 1B 到 20MB 之间' }, 400);
    }

    const conversation = safeSegment(body.conversation_id, 'anonymous');
    const filename = safeSegment(name, 'document.pdf');
    const key = `${prefix}uploads/${conversation}/${crypto.randomUUID()}-${filename}`;
    const upload = await store.createUploadUrl(key, {
      expireSeconds: 600,
      contentType,
    });
    return json({ ...upload, content_url: `/files?key=${encodeURIComponent(key)}` });
  }

  if (request.method === 'GET') {
    const key = new URL(request.url).searchParams.get('key') || '';
    if (!key.startsWith(`${prefix}uploads/`) && !key.startsWith(`${prefix}generated/`)) return json({ error: '无效文件标识' }, 400);
    const [body, metadata] = await Promise.all([
      store.get(key, { type: 'arrayBuffer' }),
      store.getMetadata(key),
    ]);
    if (!body) return json({ error: '文件不存在' }, 404);
    return new Response(body, {
      headers: {
        'Content-Type': metadata?.contentType || (key.startsWith(`${prefix}generated/`) ? `image/${key.endsWith('.jpg') ? 'jpeg' : key.endsWith('.webp') ? 'webp' : 'png'}` : 'application/pdf'),
        'Content-Disposition': `inline; filename="${safeSegment(key.split('/').pop(), key.startsWith(`${prefix}generated/`) ? 'image.png' : 'document.pdf')}"`,
        'Cache-Control': 'private, max-age=60',
      },
    });
  }

  if (request.method === 'DELETE') {
    const key = new URL(request.url).searchParams.get('key') || '';
    if (!key.startsWith(`${prefix}uploads/`) && !key.startsWith(`${prefix}generated/`)) return json({ error: '无效文件标识' }, 400);
    await store.delete(key);
    return json({ ok: true });
  }

  return json({ error: 'Method not allowed' }, 405);
}
