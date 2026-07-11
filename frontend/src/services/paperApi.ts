import { authorizedFetch } from './auth';
/**
 * 论文助读 API：搜索 → 下载 → 流式 LLM 调用。
 */

const BASE = '/api/paper';

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
  const fd = new FormData();
  fd.append('topic', topic);
  const resp = await authorizedFetch(`${BASE}/search`, { method: 'POST', body: fd });
  return resp.json();
}

/** 下载论文 PDF（后端自动从 arXiv 下载） */
export async function downloadPaper(arxivId: string, title: string): Promise<{
  file_id: string;
  filename: string;
  title: string;
  arxiv_id: string;
  total_chars: number;
  preview: string;
  error?: string;
}> {
  const fd = new FormData();
  fd.append('arxiv_id', arxivId);
  fd.append('title', title);
  const resp = await authorizedFetch(`${BASE}/download`, { method: 'POST', body: fd });
  return resp.json();
}

/** 保存论文到「我的阅读」 */
export async function savePaper(fileId: string, title: string, arxivId: string, sessionId: string): Promise<{ ok: boolean; error?: string }> {
  const fd = new FormData();
  fd.append('file_id', fileId);
  fd.append('title', title);
  fd.append('arxiv_id', arxivId);
  fd.append('session_id', sessionId);
  const resp = await authorizedFetch(`${BASE}/save`, { method: 'POST', body: fd });
  return resp.json();
}

/** 列出「我的阅读」中的论文 */
export async function listSavedPapers(sessionId: string): Promise<{ papers: SavedPaper[] }> {
  const resp = await authorizedFetch(`${BASE}/saved/${sessionId}`);
  return resp.json();
}

/** 删除「我的阅读」中的论文 */
export async function deleteSavedPaper(paperId: string): Promise<{ ok: boolean }> {
  const resp = await authorizedFetch(`${BASE}/saved/${paperId}`, { method: 'DELETE' });
  return resp.json();
}

export interface SavedPaper {
  id: string;
  file_id: string;
  title: string;
  arxiv_id: string;
  filename: string;
  created_at: number;
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
  let error: string | undefined;

  (async () => {
    try {
      const fd = new FormData();
      for (const [k, v] of Object.entries(params)) fd.append(k, v);

      const resp = await authorizedFetch(`${BASE}/${endpoint}`, {
        method: 'POST',
        body: fd,
        signal: ctrl.signal,
      });

      if (!resp.ok || !resp.body) {
        onDone('', `HTTP ${resp.status}`);
        return;
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.delta) { full += data.delta; onDelta(data.delta); }
            if (data.done) { onDone(full); return; }
            if (data.error) { error = data.error; }
          } catch { /* skip */ }
        }
      }
      onDone(full, error);
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

/** 解释术语 */
export function explainTerm(text: string, onDelta: (t: string) => void, onDone: (f: string, e?: string) => void) {
  return streamPaper('explain', { text }, onDelta, onDone);
}

/** 解释公式 */
export function explainFormula(text: string, onDelta: (t: string) => void, onDone: (f: string, e?: string) => void) {
  return streamPaper('formula', { text }, onDelta, onDone);
}

/** 全文分析 */
export function analyzePaper(fileId: string, onDelta: (t: string) => void, onDone: (f: string, e?: string) => void) {
  return streamPaper('analyze', { file_id: fileId }, onDelta, onDone);
}

/** 全文翻译 */
export function fullTranslate(fileId: string, onDelta: (t: string) => void, onDone: (f: string, e?: string) => void) {
  return streamPaper('full-translate', { file_id: fileId }, onDelta, onDone);
}

/** 提取术语 */
export function extractTerms(fileId: string, onDelta: (t: string) => void, onDone: (f: string, e?: string) => void) {
  return streamPaper('terms', { file_id: fileId }, onDelta, onDone);
}

/** 论文问答 */
export function paperQA(fileId: string, question: string, onDelta: (t: string) => void, onDone: (f: string, e?: string) => void) {
  return streamPaper('qa', { file_id: fileId, question }, onDelta, onDone);
}
