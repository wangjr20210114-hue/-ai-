import { getStore } from '@edgeone/pages-blob';
import { currentUser, tenantPrefix } from '../../auth/current-user.js';
import { requireSkillAccess } from '../../auth/entitlements.js';
import { DOWNLOAD_PART_BYTES, MAX_FILE_BYTES as MAX_PDF_BYTES } from '../files/config.js';
import {
  LIBRARY_DATA_GENERATION,
  libraryKeys,
  loadLibraryState,
  persistLibraryItem,
} from '../library/state.js';
const RESOLUTION_TIMEOUT_MS = 15_000;
const DOWNLOAD_TIMEOUT_MS = 105_000;
const REQUEST_HEADERS = {
  'User-Agent': 'Yuanbao-Agent/1.0 (paper reader; public PDF resolver)',
};
const decodeXml = (value) => String(value || '').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;|&apos;/g, "'").replace(/&amp;/g, '&');
const textOf = (xml, tag) => decodeXml((xml.match(new RegExp(`<${tag}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/${tag}>`, 'i')) || [])[1] || '').replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();

function json(data, status = 200) { return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json; charset=utf-8' } }); }
function isSyntheticPaperId(value) {
  return /^web(?:pdf|paper)-/i.test(String(value || ''));
}

function isSafePublicHttps(value) {
  try {
    const parsed = new URL(String(value || ''));
    const host = parsed.hostname.toLowerCase();
    const privateHost = (
      host === 'localhost'
      || host.endsWith('.local')
      || /^(127\.|10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.)/.test(host)
      || host === '::1'
    );
    return parsed.protocol === 'https:' && !privateHost;
  } catch {
    return false;
  }
}

function extractArxivId(value) {
  const match = String(value || '').match(
    /arxiv\.org\/(?:abs|pdf)\/([A-Za-z0-9./-]{3,80}?)(?:\.pdf)?(?:[?#]|$)/i,
  );
  return match ? match[1].replace(/\.pdf$/i, '') : '';
}

function extractDoi(value) {
  let decoded = String(value || '');
  try { decoded = decodeURIComponent(decoded); } catch { /* keep original */ }
  const match = decoded.match(/\b10\.\d{4,9}\/[-._;()/:A-Z0-9]+/i);
  return match ? match[0].replace(/[),.;]+$/, '') : '';
}

function normalizedTitle(value) {
  return String(value || '')
    .normalize('NFKC')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim();
}

function titleMatches(expected, candidate) {
  const left = normalizedTitle(expected);
  const right = normalizedTitle(candidate);
  if (!left || !right) return false;
  if (left === right || left.replaceAll(' ', '') === right.replaceAll(' ', '')) return true;
  const leftTokens = new Set(left.split(' ').filter(Boolean));
  const rightTokens = new Set(right.split(' ').filter(Boolean));
  const shared = [...leftTokens].filter((token) => rightTokens.has(token)).length;
  return shared / Math.max(leftTokens.size, rightTokens.size) >= 0.9;
}

function findReusablePaper(items, { arxivId, sourceUrl, directPdf }) {
  const canonicalArxivId = isSyntheticPaperId(arxivId) ? '' : String(arxivId || '').trim();
  const sourceCandidates = new Set(
    [sourceUrl, directPdf]
      .map((value) => String(value || '').trim())
      .filter(Boolean),
  );
  return items.find((item) => (
    (canonicalArxivId && String(item.arxiv_id || '').trim() === canonicalArxivId)
    || (item.source_url && sourceCandidates.has(String(item.source_url).trim()))
  ));
}

function storedPaperResponse(item, metadata, reused = true) {
  const fileSize = Number(
    item.file_size
    || metadata?.size
    || metadata?.contentLength
    || metadata?.headers?.['content-length']
    || 0,
  );
  return {
    file_id: item.file_id || item.storage_key,
    storage_key: item.storage_key || item.file_id,
    filename: item.filename,
    title: item.title,
    arxiv_id: item.arxiv_id || '',
    total_chars: 0,
    preview: item.preview || '',
    page_count: Math.max(0, Number(item.page_count || 0)),
    folder_id: String(item.folder_id || ''),
    content_url: item.content_url || `/files?key=${encodeURIComponent(item.file_id || item.storage_key)}`,
    ...(fileSize > 0 ? { file_size: fileSize, part_size: DOWNLOAD_PART_BYTES } : {}),
    reused,
  };
}

async function fetchJson(url, fetchImpl) {
  const response = await fetchImpl(url, {
    headers: { ...REQUEST_HEADERS, Accept: 'application/json' },
    signal: AbortSignal.timeout(RESOLUTION_TIMEOUT_MS),
  });
  if (!response.ok) return null;
  return response.json();
}

async function fetchText(url, fetchImpl) {
  const response = await fetchImpl(url, {
    headers: REQUEST_HEADERS,
    signal: AbortSignal.timeout(RESOLUTION_TIMEOUT_MS),
  });
  if (!response.ok) return '';
  return response.text();
}

function addCandidate(output, seen, url, arxivId = '', source = '') {
  if (!isSafePublicHttps(url)) return;
  const normalized = new URL(url).toString();
  if (seen.has(normalized)) return;
  seen.add(normalized);
  output.push({ url: normalized, arxivId, source });
}

async function resolveOpenAlexCandidates(doi, fetchImpl) {
  const params = new URLSearchParams({
    filter: `doi:https://doi.org/${doi}`,
    'per-page': '1',
    select: 'ids,primary_location,best_oa_location,locations,title',
  });
  const payload = await fetchJson(`https://api.openalex.org/works?${params}`, fetchImpl);
  const work = Array.isArray(payload?.results) ? payload.results[0] : null;
  if (!work) return [];
  const candidates = [];
  const seen = new Set();
  const ids = work.ids && typeof work.ids === 'object' ? work.ids : {};
  const arxivId = extractArxivId(ids.arxiv);
  if (arxivId) {
    addCandidate(candidates, seen, `https://arxiv.org/pdf/${arxivId}.pdf`, arxivId, 'OpenAlex arXiv');
  }
  const locations = [
    work.best_oa_location,
    work.primary_location,
    ...(Array.isArray(work.locations) ? work.locations : []),
  ];
  for (const location of locations) {
    if (!location || typeof location !== 'object') continue;
    const locationArxivId = extractArxivId(location.landing_page_url || location.pdf_url);
    addCandidate(
      candidates,
      seen,
      location.pdf_url || (locationArxivId ? `https://arxiv.org/pdf/${locationArxivId}.pdf` : ''),
      locationArxivId,
      'OpenAlex',
    );
  }
  return candidates;
}

async function resolveCrossrefCandidates(doi, fetchImpl) {
  const payload = await fetchJson(
    `https://api.crossref.org/works/${encodeURIComponent(doi)}`,
    fetchImpl,
  );
  const links = Array.isArray(payload?.message?.link) ? payload.message.link : [];
  const candidates = [];
  const seen = new Set();
  for (const link of links) {
    if (!String(link?.['content-type'] || '').toLowerCase().includes('pdf')) continue;
    addCandidate(candidates, seen, link.URL, extractArxivId(link.URL), 'Crossref');
  }
  return candidates;
}

async function resolveArxivTitleCandidates(title, fetchImpl) {
  const cleanTitle = String(title || '').replace(/["\\]+/g, ' ').trim().slice(0, 240);
  if (!cleanTitle) return [];
  const params = new URLSearchParams({
    search_query: `ti:"${cleanTitle}"`,
    start: '0',
    max_results: '5',
    sortBy: 'relevance',
    sortOrder: 'descending',
  });
  const xml = await fetchText(`https://export.arxiv.org/api/query?${params}`, fetchImpl);
  const candidates = [];
  const seen = new Set();
  for (const match of xml.matchAll(/<entry>([\s\S]*?)<\/entry>/gi)) {
    const entry = match[1];
    const candidateTitle = textOf(entry, 'title');
    if (!titleMatches(cleanTitle, candidateTitle)) continue;
    const arxivId = textOf(entry, 'id').replace(/\/$/, '').split('/').pop();
    if (!/^[A-Za-z0-9./-]{3,80}$/.test(arxivId || '')) continue;
    addCandidate(candidates, seen, `https://arxiv.org/pdf/${arxivId}.pdf`, arxivId, 'arXiv title');
  }
  return candidates;
}

async function resolveDownloadCandidates({
  arxivId,
  directPdf,
  sourceUrl,
  title,
}, fetchImpl = fetch) {
  const output = [];
  const seen = new Set();
  if (!isSyntheticPaperId(arxivId)) {
    addCandidate(
      output,
      seen,
      `https://arxiv.org/pdf/${encodeURIComponent(arxivId).replace(/%2F/g, '/')}.pdf`,
      arxivId,
      'arXiv id',
    );
    return output;
  }
  if (directPdf) {
    addCandidate(output, seen, directPdf, extractArxivId(directPdf), 'direct PDF');
    if (output.length) return output;
  }
  const sourceArxivId = extractArxivId(sourceUrl);
  if (sourceArxivId) {
    addCandidate(
      output,
      seen,
      `https://arxiv.org/pdf/${sourceArxivId}.pdf`,
      sourceArxivId,
      'arXiv source',
    );
    return output;
  }
  const doi = extractDoi(sourceUrl);
  const lookups = [];
  if (doi) {
    lookups.push(resolveOpenAlexCandidates(doi, fetchImpl));
    lookups.push(resolveCrossrefCandidates(doi, fetchImpl));
  }
  if (title) lookups.push(resolveArxivTitleCandidates(title, fetchImpl));
  const settled = await Promise.allSettled(lookups);
  for (const result of settled) {
    if (result.status !== 'fulfilled') continue;
    for (const candidate of result.value) {
      addCandidate(output, seen, candidate.url, candidate.arxivId, candidate.source);
    }
  }
  return output.slice(0, 6);
}

async function downloadFirstValidPdf(candidates, fetchImpl = fetch) {
  const deadline = Date.now() + DOWNLOAD_TIMEOUT_MS;
  let lastFailure = '';
  for (const candidate of candidates) {
    const remaining = deadline - Date.now();
    if (remaining <= 1_000) break;
    const attemptTimeout = candidates.length === 1 ? remaining : Math.min(25_000, remaining);
    try {
      const response = await fetchImpl(candidate.url, {
        headers: { ...REQUEST_HEADERS, Accept: 'application/pdf' },
        signal: AbortSignal.timeout(attemptTimeout),
      });
      if (!response.ok) {
        lastFailure = `HTTP ${response.status}`;
        continue;
      }
      const finalUrl = response.url || candidate.url;
      if (!isSafePublicHttps(finalUrl)) {
        lastFailure = '下载发生不安全重定向';
        continue;
      }
      const contentLength = Number(response.headers.get('content-length') || 0);
      if (contentLength > MAX_PDF_BYTES) {
        lastFailure = 'PDF 超过 20MB';
        continue;
      }
      const data = await response.arrayBuffer();
      if (data.byteLength < 1000 || data.byteLength > MAX_PDF_BYTES) {
        lastFailure = 'PDF 大小无效或超过 20MB';
        continue;
      }
      if (new TextDecoder().decode(data.slice(0, 5)) !== '%PDF-') {
        lastFailure = '下载结果不是有效 PDF';
        continue;
      }
      return { data, candidate };
    } catch (error) {
      lastFailure = (
        error?.name === 'TimeoutError' || error?.name === 'AbortError'
          ? '单个公开来源下载超时'
          : (error?.message || '下载请求失败')
      );
    }
  }
  return { data: null, candidate: null, lastFailure };
}

async function search(topic) {
  const query = new URLSearchParams({ search_query: `all:${topic}`, start: '0', max_results: '6', sortBy: 'relevance', sortOrder: 'descending' });
  const response = await fetch(`https://export.arxiv.org/api/query?${query}`, { headers: { 'User-Agent': 'Yuanbao-Agent/1.0 (paper reader)' } });
  if (!response.ok) throw new Error(`arXiv 返回 ${response.status}`);
  const xml = await response.text();
  return [...xml.matchAll(/<entry>([\s\S]*?)<\/entry>/gi)].map((match) => {
    const entry = match[1];
    const id = textOf(entry, 'id').replace(/\/$/, '').split('/').pop();
    const published = textOf(entry, 'published');
    const authors = [...entry.matchAll(/<author>([\s\S]*?)<\/author>/gi)].map((author) => textOf(author[1], 'name')).filter(Boolean);
    const abstract = textOf(entry, 'summary');
    return { title: textOf(entry, 'title'), arxiv_id: id, authors: authors.slice(0, 8).join(', '), year: Number(published.slice(0, 4)) || 0, abstract_zh: abstract, key_contribution: abstract.slice(0, 240), citations: 'arXiv', arxiv_url: `https://arxiv.org/abs/${id}`, pdf_url: `https://arxiv.org/pdf/${id}.pdf` };
  }).filter((paper) => paper.arxiv_id && paper.title);
}

export async function onRequest(context) {
  const { request, env } = context;
  let user;
  try { user = await currentUser(request, env); } catch { return json({ error: 'Unauthorized' }, 401); }
  try { requireSkillAccess(user, 'paper-reading'); } catch (error) {
    return json({ error: error.message, code: error.code }, error.status || 403);
  }
  const prefix = tenantPrefix(user, env);
  const keys = libraryKeys(prefix);
  if (request.method === 'GET') {
    const topic = new URL(request.url).searchParams.get('topic')?.trim() || '';
    if (!topic) return json({ error: '论文主题不能为空' }, 400);
    try { return json({ papers: await search(topic), topic }); } catch (error) { return json({ error: `arXiv 搜索失败：${error.message}` }, 502); }
  }
  if (request.method !== 'POST') return json({ error: 'Method not allowed' }, 405);
  const body = await request.json();
  const arxivId = String(body.arxiv_id || '').trim();
  const directPdf = String(body.pdf_url || '').trim();
  const sourceUrl = String(body.source_url || '').trim();
  const title = String(body.title || '').trim().slice(0, 240);
  const isArxiv = !isSyntheticPaperId(arxivId);
  if (isArxiv && (!/^[A-Za-z0-9./-]{3,80}$/.test(arxivId) || arxivId.includes('..'))) return json({ error: '无效 arXiv ID' }, 400);
  try {
    const store = getStore({ name: 'yuanbao-files', consistency: 'strong' });
    const state = await loadLibraryState(store, keys);
    const { items } = state;
    const reusable = findReusablePaper(items, { arxivId, sourceUrl, directPdf });
    if (reusable) {
      const key = reusable.file_id || reusable.storage_key;
      const metadata = key ? await store.getMetadata(key) : null;
      if (metadata) return json(storedPaperResponse(reusable, metadata));
    }

    const candidates = await resolveDownloadCandidates({
      arxivId,
      directPdf,
      sourceUrl,
      title,
    });
    if (!candidates.length) {
      return json({
        error: '没有找到可公开下载的 PDF。你仍可以通过“查看论文”访问来源页。',
        code: 'public_pdf_unavailable',
        source_url: sourceUrl,
      }, 422);
    }
    const downloaded = await downloadFirstValidPdf(candidates);
    if (!downloaded.data || !downloaded.candidate) {
      return json({
        error: `找到了可能的公开 PDF，但下载或验证失败${downloaded.lastFailure ? `（${downloaded.lastFailure}）` : ''}。请稍后重试或访问来源页。`,
        code: 'paper_download_failed',
        source_url: sourceUrl,
      }, 502);
    }
    const { data, candidate } = downloaded;
    const resolvedArxivId = candidate.arxivId || (isArxiv ? arxivId : '');
    const stableId = resolvedArxivId || arxivId || 'resolved-paper';
    const safeId = stableId.replace(/[^A-Za-z0-9.-]+/g, '-');
    const key = `${prefix}uploads/yuanbao_${LIBRARY_DATA_GENERATION}_papers/${crypto.randomUUID()}-${safeId}.pdf`;
    await store.set(key, data);
    const now = Date.now();
    const savedTitle = title || `arXiv ${resolvedArxivId || arxivId}`;
    const canonicalSource = (
      resolvedArxivId
        ? `https://arxiv.org/abs/${resolvedArxivId}`
        : (sourceUrl || directPdf || candidate.url)
    );
    const item = { id: crypto.randomUUID(), storage_key: key, file_id: key, filename: `${safeId}.pdf`, title: savedTitle, mime_type: 'application/pdf', kind: 'paper', is_paper: true, arxiv_id: resolvedArxivId, source_url: canonicalSource, page_count: 0, preview: '', content_url: `/files?key=${encodeURIComponent(key)}`, file_size: data.byteLength, part_size: DOWNLOAD_PART_BYTES, created_at: now, last_opened_at: now };
    state.items = items.filter((saved) => (
      resolvedArxivId ? saved.arxiv_id !== resolvedArxivId : saved.source_url !== canonicalSource
    ));
    await persistLibraryItem(store, keys, item, state);
    return json(storedPaperResponse(item, { size: data.byteLength }, false));
  } catch (error) {
    const timeout = error?.name === 'TimeoutError' || error?.name === 'AbortError';
    return json({
      error: timeout ? '论文解析或下载超时，请稍后重试' : `论文下载失败：${error.message}`,
      code: timeout ? 'paper_timeout' : 'paper_download_failed',
      source_url: sourceUrl,
    }, 502);
  }
}

export const __test = {
  extractArxivId,
  extractDoi,
  isSafePublicHttps,
  normalizedTitle,
  titleMatches,
  findReusablePaper,
  storedPaperResponse,
  resolveDownloadCandidates,
  downloadFirstValidPdf,
};
