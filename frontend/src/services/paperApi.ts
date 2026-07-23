import { authorizedFetch, withEdgeOneAuth } from './auth';
import { getOrCreateConversationId, makersConversationHeaders } from './conversation';
/**
 * 论文助读 API：搜索 → 下载 → 流式 LLM 调用。
 */

export interface PaperInfo {
  title: string;
  arxiv_id: string;
  authors: string;
  year: number;
  abstract_zh: string;
  key_contribution: string;
  citations: string;
  arxiv_url: string;
  pdf_url: string;
}

/** 搜索论文 */
export async function searchPapers(topic: string): Promise<{ papers: PaperInfo[]; topic: string; error?: string }> {
  const resp = await authorizedFetch(`/papers?topic=${encodeURIComponent(topic)}`);
  return resp.json();
}

/** 下载论文 PDF（后端自动从 arXiv 下载） */
export async function downloadPaper(arxivId: string, title: string, pdfUrl = ''): Promise<{
  file_id: string;
  filename: string;
  title: string;
  arxiv_id: string;
  total_chars: number;
  preview: string;
  error?: string;
}> {
  const resp = await authorizedFetch('/papers', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ arxiv_id: arxivId, title, pdf_url: pdfUrl }),
  });
  const data = await resp.json();
  if (resp.ok) window.dispatchEvent(new CustomEvent('yuanbao:library-changed'));
  return data;
}

/** 保存论文到「我的阅读」 */
export async function savePaper(fileId: string, title: string, arxivId: string, sessionId: string): Promise<{ ok: boolean; error?: string }> {
  void sessionId;
  const item = await registerReadingItem({ storage_key: fileId, filename: title, title, mime_type: 'application/pdf', is_paper: true, arxiv_id: arxivId });
  return { ok: Boolean(item.id) };
}

/** 列出「我的阅读」中的论文 */
export async function listSavedPapers(sessionId: string): Promise<{ papers: SavedPaper[] }> {
  void sessionId;
  const resp = await authorizedFetch('/library');
  const data = await resp.json() as { items?: SavedPaper[] };
  return { papers: data.items || [] };
}

/** 删除「我的阅读」中的论文 */
export async function deleteSavedPaper(paperId: string): Promise<{ ok: boolean }> {
  const resp = await authorizedFetch(`/library?id=${encodeURIComponent(paperId)}`, { method: 'DELETE' });
  return resp.json();
}

export interface SavedPaper {
  id: string;
  file_id: string;
  title: string;
  arxiv_id: string;
  filename: string;
  created_at: number;
  storage_key?: string;
  content_url?: string;
  mime_type?: string;
  kind?: 'paper' | 'pdf';
  is_paper?: boolean;
  page_count?: number;
  preview?: string;
  folder_id?: string;
}

export interface ReadingFolder { id: string; name: string; automatic?: boolean; created_at?: number; }
export interface ReadingSettings { auto_organize: boolean; }
export interface ReadingLibrary { papers: SavedPaper[]; folders: ReadingFolder[]; settings: ReadingSettings; }

export async function getReadingLibrary(): Promise<ReadingLibrary> {
  const resp = await authorizedFetch('/library');
  const data = await resp.json().catch(() => ({})) as { items?: SavedPaper[]; folders?: ReadingFolder[]; settings?: ReadingSettings; error?: string };
  if (!resp.ok) throw new Error(data.error || '读取我的阅读失败');
  return { papers: data.items || [], folders: data.folders || [], settings: { auto_organize: data.settings?.auto_organize !== false } };
}

async function libraryOperation<T>(body: Record<string, unknown>): Promise<T> {
  const resp = await authorizedFetch('/library', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const data = await resp.json().catch(() => ({})) as T & { error?: string };
  if (!resp.ok) throw new Error(data.error || '更新阅读库失败');
  window.dispatchEvent(new CustomEvent('yuanbao:library-changed'));
  return data;
}

export async function updateReadingSettings(autoOrganize: boolean) {
  return libraryOperation<{ settings: ReadingSettings }>({ operation: 'settings', auto_organize: autoOrganize });
}
export async function createReadingFolder(name: string) {
  return libraryOperation<{ folder: ReadingFolder }>({ operation: 'create_folder', name });
}
export async function renameReadingFolder(folderId: string, name: string) {
  return libraryOperation<{ folder: ReadingFolder }>({ operation: 'rename_folder', folder_id: folderId, name });
}
export async function moveReadingItem(itemId: string, folderId: string) {
  return libraryOperation<{ item: SavedPaper }>({ operation: 'move_item', item_id: itemId, folder_id: folderId });
}

export async function registerReadingItem(item: {
  storage_key: string;
  filename: string;
  title?: string;
  mime_type?: string;
  is_paper?: boolean;
  arxiv_id?: string;
  page_count?: number;
  preview?: string;
  folder_id?: string;
}): Promise<SavedPaper> {
  const resp = await authorizedFetch('/library', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ operation: 'register', ...item }),
  });
  const data = await resp.json().catch(() => ({})) as { item?: SavedPaper; error?: string };
  if (!resp.ok || !data.item) throw new Error(data.error || '保存到我的阅读失败');
  window.dispatchEvent(new CustomEvent('yuanbao:library-changed'));
  return data.item;
}

export function paperFileUrl(fileId: string): string {
  return withEdgeOneAuth(`/files?key=${encodeURIComponent(fileId)}`);
}

/**
 * Read a Makers Blob object without crossing the 6 MB Cloud Function response
 * ceiling. Small files keep the single-request path; larger files are joined
 * from authenticated 4 MB parts exposed by the same Makers-backed endpoint.
 */
export async function fetchPaperFile(fileId: string, signal?: AbortSignal): Promise<Response> {
  const url = paperFileUrl(fileId);
  const head = await authorizedFetch(url, { method: 'HEAD', signal });
  if (!head.ok) return head;
  const size = Number(head.headers.get('x-yuanbao-file-size') || head.headers.get('content-length') || 0);
  const partSize = Number(head.headers.get('x-yuanbao-part-size') || 0);
  if (!Number.isFinite(size) || size <= 0 || !Number.isFinite(partSize) || partSize <= 0 || size <= partSize) {
    return authorizedFetch(url, { signal });
  }

  const chunks: Uint8Array[] = [];
  const totalParts = Math.ceil(size / partSize);
  for (let part = 0; part < totalParts; part += 1) {
    const separator = url.includes('?') ? '&' : '?';
    const response = await authorizedFetch(`${url}${separator}part=${part}`, { signal });
    if (!response.ok) return response;
    chunks.push(new Uint8Array(await response.arrayBuffer()));
  }
  const blob = new Blob(chunks, { type: head.headers.get('content-type') || 'application/pdf' });
  if (blob.size !== size) {
    return new Response(JSON.stringify({ error: 'PDF 分片不完整，请重试' }), {
      status: 502,
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
    });
  }
  return new Response(blob, { status: 200, headers: { 'Content-Type': blob.type, 'Content-Length': String(blob.size) } });
}

/** SSE 流式调用通用方法 */
export function streamPaper(
  endpoint: string,
  params: Record<string, string>,
  onDelta: (text: string) => void,
  onDone: (full: string, error?: string) => void,
): { cancel: () => void } {
  const ctrl = new AbortController();
  let full = '';

  (async () => {
    try {
      const resp = await authorizedFetch('/reader', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...makersConversationHeaders(getOrCreateConversationId()) },
        body: JSON.stringify({ action: endpoint, ...params }),
        signal: ctrl.signal,
      });
      const data = await resp.json().catch(() => ({})) as { content?: string; error?: string };
      if (!resp.ok || data.error) return onDone('', data.error || `HTTP ${resp.status}`);
      full = data.content || '';
      if (full) onDelta(full);
      onDone(full);
    } catch (error: unknown) {
      if (!(error instanceof DOMException && error.name === 'AbortError')) {
        onDone(full, error instanceof Error ? error.message : '请求失败');
      }
    }
  })();

  return { cancel: () => ctrl.abort() };
}

/** 翻译段落 */
export function translateParagraph(text: string, onDelta: (t: string) => void, onDone: (f: string, e?: string) => void) {
  return streamPaper('translate', { text }, onDelta, onDone);
}

/** 总结段落 */
export function summarizeParagraph(text: string, onDelta: (t: string) => void, onDone: (f: string, e?: string) => void) {
  return streamPaper('summarize', { text }, onDelta, onDone);
}

/** 全文分析 */
export function analyzePaper(fileId: string, onDelta: (t: string) => void, onDone: (f: string, e?: string) => void, text = '') {
  return streamPaper('analyze', { file_id: fileId, text }, onDelta, onDone);
}

/** 论文问答 */
export function paperQA(fileId: string, question: string, onDelta: (t: string) => void, onDone: (f: string, e?: string) => void, text = '') {
  return streamPaper('qa', { file_id: fileId, question, text }, onDelta, onDone);
}
