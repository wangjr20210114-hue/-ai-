import { authorizedFetch, withEdgeOneAuth } from './auth';
import { translate } from '../i18n';
import { getOrCreateConversationId, makersConversationHeaders } from './conversation';
import { getStoredLanguage } from '../i18n';
/**
 * 论文助读 API：搜索 → 下载 → 流式 LLM 调用。
 */

/** 下载论文 PDF；后端会解析 arXiv、公开 PDF、DOI 或学术来源页。 */
export async function downloadPaper(arxivId: string, title: string, pdfUrl = '', sourceUrl = ''): Promise<{
  file_id: string;
  filename: string;
  title: string;
  arxiv_id: string;
  total_chars: number;
  preview: string;
  file_size?: number;
  part_size?: number;
  reused?: boolean;
  error?: string;
  code?: string;
}> {
  const resp = await authorizedFetch('/papers', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      arxiv_id: arxivId,
      title,
      pdf_url: pdfUrl,
      source_url: sourceUrl,
    }),
  });
  const data = await resp.json().catch(() => ({
    error: translate('paperInvalidResponse', { status: resp.status }),
    code: 'invalid_response',
  }));
  if (resp.ok) window.dispatchEvent(new CustomEvent('yuanbao:library-changed'));
  return data;
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
  file_size?: number;
  part_size?: number;
  preview?: string;
  folder_id?: string;
  assistant_results?: PaperAssistantResult[];
}

export interface PaperAssistantResult {
  id: string;
  action: 'translate' | 'summarize' | 'analyze';
  title: string;
  source_text: string;
  content: string;
  created_at: number;
}

export interface ReadingFolder { id: string; name: string; automatic?: boolean; created_at?: number; }
export interface ReadingSettings { auto_organize: boolean; }
export interface ReadingLibrary { papers: SavedPaper[]; folders: ReadingFolder[]; settings: ReadingSettings; }

export async function getReadingLibrary(): Promise<ReadingLibrary> {
  const resp = await authorizedFetch('/library');
  const data = await resp.json().catch(() => ({})) as { items?: SavedPaper[]; folders?: ReadingFolder[]; settings?: ReadingSettings; error?: string };
  if (!resp.ok) throw new Error(data.error || translate('readingLoadFailed'));
  return { papers: data.items || [], folders: data.folders || [], settings: { auto_organize: data.settings?.auto_organize !== false } };
}

export async function getReadingSettings(): Promise<ReadingSettings> {
  const resp = await authorizedFetch('/library?view=settings');
  const data = await resp.json().catch(() => ({})) as { settings?: ReadingSettings; error?: string };
  if (!resp.ok) throw new Error(data.error || translate('readingLoadFailed'));
  return { auto_organize: data.settings?.auto_organize !== false };
}

async function libraryOperation<T>(body: Record<string, unknown>): Promise<T> {
  const resp = await authorizedFetch('/library', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const data = await resp.json().catch(() => ({})) as T & { error?: string };
  if (!resp.ok) throw new Error(data.error || translate('readingLibraryUpdateFailed'));
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

export async function loadPaperAssistantResults(storageKey: string): Promise<PaperAssistantResult[]> {
  const library = await getReadingLibrary();
  const item = library.papers.find((paper) => paper.storage_key === storageKey || paper.file_id === storageKey);
  return [...(item?.assistant_results || [])].sort(
    (left, right) => Number(left.created_at || 0) - Number(right.created_at || 0),
  );
}

export async function savePaperAssistantResult(
  storageKey: string,
  result: Pick<PaperAssistantResult, 'action' | 'title' | 'source_text' | 'content'>,
): Promise<PaperAssistantResult> {
  const data = await libraryOperation<{ result: PaperAssistantResult }>({
    operation: 'save_assistant_result',
    storage_key: storageKey,
    ...result,
  });
  return data.result;
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
  if (!resp.ok || !data.item) throw new Error(data.error || translate('saveToReadingFailed'));
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
export interface PaperFileMetadata {
  size?: number;
  partSize?: number;
}

interface MaterializedPaperFile {
  blob: Blob;
  contentType: string;
}

const materializedPaperFiles = new Map<string, MaterializedPaperFile>();
const pendingPaperFiles = new Map<string, Promise<MaterializedPaperFile>>();

function responseFromPaperFile(file: MaterializedPaperFile): Response {
  return new Response(file.blob, {
    status: 200,
    headers: {
      'Content-Type': file.contentType,
      'Content-Length': String(file.blob.size),
    },
  });
}

function waitForPaperFile(
  task: Promise<MaterializedPaperFile>,
  signal?: AbortSignal,
): Promise<MaterializedPaperFile> {
  if (!signal) return task;
  if (signal.aborted) return Promise.reject(new DOMException('Aborted', 'AbortError'));
  return new Promise((resolve, reject) => {
    const abort = () => reject(new DOMException('Aborted', 'AbortError'));
    signal.addEventListener('abort', abort, { once: true });
    task.then(
      (value) => {
        signal.removeEventListener('abort', abort);
        resolve(value);
      },
      (error) => {
        signal.removeEventListener('abort', abort);
        reject(error);
      },
    );
  });
}

async function downloadPaperFile(
  fileId: string,
  metadata: PaperFileMetadata,
): Promise<MaterializedPaperFile> {
  const url = paperFileUrl(fileId);
  let size = Number(metadata.size || 0);
  let partSize = Number(metadata.partSize || 0);
  let contentType = 'application/pdf';
  if (!Number.isFinite(size) || size <= 0 || !Number.isFinite(partSize) || partSize <= 0) {
    const head = await authorizedFetch(url, { method: 'HEAD' });
    if (!head.ok) throw new Error(translate('pdfLoadStatusFailed', { status: head.status }));
    size = Number(head.headers.get('x-yuanbao-file-size') || head.headers.get('content-length') || 0);
    partSize = Number(head.headers.get('x-yuanbao-part-size') || 0);
    contentType = head.headers.get('content-type') || contentType;
  }
  if (!Number.isFinite(size) || size <= 0 || !Number.isFinite(partSize) || partSize <= 0 || size <= partSize) {
    const response = await authorizedFetch(url);
    if (!response.ok) throw new Error(translate('pdfLoadStatusFailed', { status: response.status }));
    const blob = await response.blob();
    return { blob, contentType: response.headers.get('content-type') || blob.type || contentType };
  }

  const totalParts = Math.ceil(size / partSize);
  const chunks = await Promise.all(Array.from({ length: totalParts }, async (_, part) => {
    const separator = url.includes('?') ? '&' : '?';
    const response = await authorizedFetch(`${url}${separator}part=${part}`);
    if (!response.ok) throw new Error(translate('pdfLoadStatusFailed', { status: response.status }));
    return new Uint8Array(await response.arrayBuffer());
  }));
  const blob = new Blob(chunks, { type: contentType });
  if (blob.size !== size) {
    throw new Error(translate('pdfChunksIncomplete'));
  }
  return { blob, contentType };
}

/**
 * Materialize each PDF once per page session. Reader, inline preview and
 * downloads can then share the same bytes, while known metadata skips the
 * extra HEAD round trip and large Makers-safe parts download concurrently.
 */
export async function fetchPaperFile(
  fileId: string,
  signal?: AbortSignal,
  metadata: PaperFileMetadata = {},
): Promise<Response> {
  const cached = materializedPaperFiles.get(fileId);
  if (cached) return responseFromPaperFile(cached);
  let task = pendingPaperFiles.get(fileId);
  if (!task) {
    task = downloadPaperFile(fileId, metadata)
      .then((file) => {
        // The reader only needs the current document. Keeping one materialized
        // PDF prevents duplicate preview/fullscreen reads without retaining a
        // growing collection of large files in browser memory.
        materializedPaperFiles.clear();
        materializedPaperFiles.set(fileId, file);
        return file;
      })
      .finally(() => pendingPaperFiles.delete(fileId));
    pendingPaperFiles.set(fileId, task);
  }
  return responseFromPaperFile(await waitForPaperFile(task, signal));
}

export function preloadPaperFile(
  fileId: string,
  metadata: PaperFileMetadata = {},
): void {
  void fetchPaperFile(fileId, undefined, metadata).catch(() => {
    // Opening the reader remains the visible retry/error path.
  });
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
  let settled = false;
  const finish = (error?: string) => {
    if (settled) return;
    settled = true;
    onDone(full, error);
  };

  (async () => {
    try {
      const resp = await authorizedFetch('/reader', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...makersConversationHeaders(getOrCreateConversationId()) },
        body: JSON.stringify({ action: endpoint, ...params, response_language: getStoredLanguage() }),
        signal: ctrl.signal,
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({})) as { error?: string };
        return finish(data.error || `HTTP ${resp.status}`);
      }
      const contentType = resp.headers.get('content-type') || '';
      if (!contentType.includes('text/event-stream') || !resp.body) {
        const data = await resp.json().catch(() => ({})) as { content?: string; error?: string };
        if (data.error) return finish(data.error);
        full = data.content || '';
        if (full) onDelta(full);
        return finish();
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      const consume = (frame: string) => {
        const payload = frame
          .split(/\r?\n/)
          .filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).trimStart())
          .join('\n')
          .trim();
        if (!payload || payload === '[DONE]') return;
        try {
          const event = JSON.parse(payload) as { type?: string; content?: string };
          if (event.type === 'paper_delta' && event.content) {
            full += event.content;
            onDelta(event.content);
          } else if (event.type === 'error_message') {
            finish(event.content || translate('requestFailed'));
          } else if (event.type === 'paper_done') {
            finish();
          }
        } catch {
          // Ignore malformed heartbeat/proxy frames; the terminal frame still
          // determines success or failure.
        }
      };
      while (!settled) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split(/\r?\n\r?\n/);
        buffer = frames.pop() || '';
        frames.forEach(consume);
      }
      buffer += decoder.decode();
      if (buffer.trim()) consume(buffer);
      finish();
    } catch (error: unknown) {
      if (!(error instanceof DOMException && error.name === 'AbortError')) {
        finish(error instanceof Error ? error.message : translate('requestFailed'));
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
