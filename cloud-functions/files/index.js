import { getStore } from '@edgeone/pages-blob';
import { currentUser, tenantPrefix } from '../../auth/current-user.js';

const MAX_FILE_BYTES = 20 * 1024 * 1024;
// Makers Cloud Functions cap a response body at 6 MB. Keep every file part
// below that limit while continuing to persist the original object in the
// Makers Blob store.
const DOWNLOAD_PART_BYTES = 4 * 1024 * 1024;
const SUPPORTED_TYPES = new Map([
  ['application/pdf', ['.pdf']],
  ['image/png', ['.png']],
  ['image/jpeg', ['.jpg', '.jpeg']],
  ['image/webp', ['.webp']],
]);

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

function contentDisposition(key, fallback) {
  const filename = safeSegment(key.split('/').pop(), fallback);
  const ascii = filename.replace(/[^\x20-\x7E]+/g, '_').replace(/["\\]/g, '_') || fallback;
  return `inline; filename="${ascii}"; filename*=UTF-8''${encodeURIComponent(filename)}`;
}

export async function onRequest(context) {
  const { request, env } = context;
  let user;
  try { user = await currentUser(request, env); } catch { return json({ error: 'Unauthorized' }, 401); }
  const prefix = tenantPrefix(user, env);
  const store = context.__store || getStore({ name: 'yuanbao-files', consistency: 'strong' });

  if (request.method === 'POST') {
    const body = await request.json();
    const name = String(body.name || 'document.pdf');
    const contentType = String(body.content_type || 'application/pdf');
    const size = Number(body.size || 0);
    const extensions = SUPPORTED_TYPES.get(contentType);
    if (!extensions || !extensions.some((extension) => name.toLowerCase().endsWith(extension))) {
      return json({ error: '仅支持 PDF、PNG、JPG/JPEG 和 WebP 文件' }, 400);
    }
    if (!Number.isFinite(size) || size <= 0 || size > MAX_FILE_BYTES) {
      return json({ error: '文件大小必须在 1B 到 20MB 之间' }, 400);
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

  if (request.method === 'GET' || request.method === 'HEAD') {
    const url = new URL(request.url);
    const key = url.searchParams.get('key') || '';
    if (!key.startsWith(`${prefix}uploads/`) && !key.startsWith(`${prefix}generated/`)) return json({ error: '无效文件标识' }, 400);
    const metadata = await store.getMetadata(key);
    if (!metadata) return json({ error: '文件不存在' }, 404);
    const contentType = metadata.contentType || (key.startsWith(`${prefix}generated/`) ? `image/${key.endsWith('.jpg') ? 'jpeg' : key.endsWith('.webp') ? 'webp' : 'png'}` : 'application/pdf');
    const contentLength = Number(metadata.size || metadata.contentLength || metadata.headers?.['content-length'] || 0);
    const commonHeaders = {
      'Content-Type': contentType,
      // Response headers only accept byte-safe values. Preserve international
      // filenames through RFC 5987 instead of inserting raw CJK characters.
      'Content-Disposition': contentDisposition(key, key.startsWith(`${prefix}generated/`) ? 'image.png' : 'document.pdf'),
      'Cache-Control': 'private, max-age=60',
      'Accept-Ranges': 'makers-parts',
      'X-Yuanbao-Part-Size': String(DOWNLOAD_PART_BYTES),
      ...(contentLength > 0 ? { 'X-Yuanbao-File-Size': String(contentLength) } : {}),
      ...(contentLength > 0 ? { 'Content-Length': String(contentLength) } : {}),
    };
    if (request.method === 'HEAD') return new Response(null, { headers: commonHeaders });

    const body = await store.get(key, { type: 'arrayBuffer', consistency: 'eventual' });
    if (!body) return json({ error: '文件不存在' }, 404);
    const rawPart = url.searchParams.get('part');
    if (rawPart !== null) {
      const part = Number(rawPart);
      if (!Number.isSafeInteger(part) || part < 0) return json({ error: '无效文件分片' }, 400);
      const start = part * DOWNLOAD_PART_BYTES;
      if (start >= body.byteLength) return json({ error: '文件分片不存在' }, 416);
      const end = Math.min(start + DOWNLOAD_PART_BYTES, body.byteLength);
      return new Response(body.slice(start, end), {
        headers: {
          ...commonHeaders,
          'Content-Length': String(end - start),
          'Content-Range': `bytes ${start}-${end - 1}/${body.byteLength}`,
          'X-Yuanbao-Part-Index': String(part),
        },
      });
    }
    return new Response(body, {
      headers: { ...commonHeaders, 'Content-Length': String(body.byteLength) },
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

export const __test = { DOWNLOAD_PART_BYTES, contentDisposition };
