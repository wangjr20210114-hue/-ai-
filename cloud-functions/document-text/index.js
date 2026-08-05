import { getDocument } from 'pdfjs-dist/legacy/build/pdf.mjs';
import { getStore } from '@edgeone/pages-blob';
import { currentUser, tenantPrefix } from '../../auth/current-user.js';
import { requireSkillAccess } from '../../auth/entitlements.js';
import { MAX_FILE_BYTES } from '../files/config.js';

const MAX_TEXT_CHARS = 120_000;

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
}

function failure(code, status) {
  return json({ error: code, code }, status);
}

function normalizedLine(items) {
  return items
    .filter((item) => item && typeof item === 'object' && 'str' in item)
    .map((item) => String(item.str || '').trim())
    .filter(Boolean)
    .join(' ')
    .replace(/\s+/g, ' ')
    .trim();
}

export async function extractPdfText(data, openDocument = getDocument) {
  const task = openDocument({
    data: data instanceof Uint8Array ? data : new Uint8Array(data),
    disableWorker: true,
    isEvalSupported: false,
    useSystemFonts: true,
  });
  const document = await task.promise;
  const pages = [];
  const pageCount = Number(document.numPages || 0);
  let totalChars = 0;
  let truncated = false;
  try {
    for (let pageNumber = 1; pageNumber <= pageCount; pageNumber += 1) {
      const page = await document.getPage(pageNumber);
      const content = await page.getTextContent();
      const line = normalizedLine(content.items || []);
      if (line) {
        pages.push(line);
        totalChars += line.length + (pages.length > 1 ? 2 : 0);
      }
      if (totalChars >= MAX_TEXT_CHARS) {
        truncated = pageNumber < pageCount;
        break;
      }
    }
  } finally {
    await document.destroy();
  }
  const text = pages.join('\n\n').slice(0, MAX_TEXT_CHARS);
  return {
    text,
    preview: text.slice(0, 1_200),
    page_count: pageCount,
    truncated: truncated || text.length >= MAX_TEXT_CHARS,
  };
}

export async function onRequest(context) {
  const { request, env } = context;
  if (request.method !== 'POST') return failure('METHOD_NOT_ALLOWED', 405);
  let user;
  try { user = await currentUser(request, env); } catch { return json({ error: 'Unauthorized' }, 401); }
  try { requireSkillAccess(user, 'paper-reading'); } catch (error) {
    return json({ error: error.message, code: error.code }, error.status || 403);
  }
  const body = await request.json().catch(() => ({}));
  const fileId = String(body.file_id || body.storage_key || '');
  const prefix = tenantPrefix(user, env);
  if (!fileId.startsWith(`${prefix}uploads/`)) {
    return failure('INVALID_FILE_ID', 400);
  }
  const store = context.__store || getStore({ name: 'yuanbao-files', consistency: 'strong' });
  const metadata = await store.getMetadata(fileId);
  if (!metadata) return failure('FILE_NOT_FOUND', 404);
  const size = Number(metadata.size || metadata.contentLength || metadata.headers?.['content-length'] || 0);
  const contentType = String(metadata.contentType || 'application/pdf').toLowerCase();
  if ((size > 0 && size > MAX_FILE_BYTES) || !contentType.includes('pdf')) {
    return failure('UNSUPPORTED_DOCUMENT', 422);
  }
  const data = await store.get(fileId, { type: 'arrayBuffer', consistency: 'eventual' });
  if (!data) return failure('FILE_NOT_FOUND', 404);
  try {
    const result = await (context.__extractPdfText || extractPdfText)(data);
    if (!result.text) {
      return failure('PDF_TEXT_UNAVAILABLE', 422);
    }
    return json({ file_id: fileId, storage_key: fileId, ...result });
  } catch {
    return failure('PDF_EXTRACTION_FAILED', 422);
  }
}

export const __test = { MAX_TEXT_CHARS, normalizedLine };
