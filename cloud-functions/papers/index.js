import { getStore } from '@edgeone/pages-blob';
import { currentUser, tenantPrefix } from '../../auth/current-user.js';
const MAX_PDF_BYTES = 20 * 1024 * 1024;
const decodeXml = (value) => String(value || '').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;|&apos;/g, "'").replace(/&amp;/g, '&');
const textOf = (xml, tag) => decodeXml((xml.match(new RegExp(`<${tag}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/${tag}>`, 'i')) || [])[1] || '').replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();

function json(data, status = 200) { return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json; charset=utf-8' } }); }
async function loadIndex(store, indexKey) {
  const raw = await store.get(indexKey, { type: 'arrayBuffer' });
  if (!raw) return [];
  try { const value = JSON.parse(new TextDecoder().decode(raw)); return Array.isArray(value) ? value : []; } catch { return []; }
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
  const prefix = tenantPrefix(user, env);
  const indexKey = `${prefix}library/index.json`;
  if (request.method === 'GET') {
    const topic = new URL(request.url).searchParams.get('topic')?.trim() || '';
    if (!topic) return json({ error: '论文主题不能为空' }, 400);
    try { return json({ papers: await search(topic), topic }); } catch (error) { return json({ error: `arXiv 搜索失败：${error.message}` }, 502); }
  }
  if (request.method !== 'POST') return json({ error: 'Method not allowed' }, 405);
  const body = await request.json();
  const arxivId = String(body.arxiv_id || '').trim();
  const directPdf = String(body.pdf_url || '').trim();
  const isArxiv = !arxivId.startsWith('webpdf-');
  if (isArxiv && (!/^[A-Za-z0-9./-]{3,80}$/.test(arxivId) || arxivId.includes('..'))) return json({ error: '无效 arXiv ID' }, 400);
  try {
    let downloadUrl = `https://arxiv.org/pdf/${encodeURIComponent(arxivId).replace(/%2F/g, '/')}.pdf`;
    if (!isArxiv) {
      const parsed = new URL(directPdf);
      const host = parsed.hostname.toLowerCase();
      const privateHost = host === 'localhost' || host.endsWith('.local') || /^(127\.|10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.)/.test(host);
      if (parsed.protocol !== 'https:' || privateHost) return json({ error: '论文 PDF 地址不安全' }, 400);
      downloadUrl = parsed.toString();
    }
    const response = await fetch(downloadUrl, { headers: { 'User-Agent': 'Yuanbao-Agent/1.0 (paper reader)' } });
    if (!response.ok) return json({ error: `论文下载失败：${response.status}` }, 502);
    if (!isArxiv) {
      const finalUrl = new URL(response.url);
      if (finalUrl.protocol !== 'https:' || finalUrl.hostname === 'localhost') return json({ error: '论文下载发生不安全重定向' }, 400);
    }
    const data = await response.arrayBuffer();
    if (data.byteLength < 1000 || data.byteLength > MAX_PDF_BYTES) return json({ error: '论文 PDF 大小无效或超过 20MB' }, 400);
    if (new TextDecoder().decode(data.slice(0, 5)) !== '%PDF-') return json({ error: '下载结果不是有效 PDF' }, 400);
    const store = getStore({ name: 'yuanbao-files', consistency: 'strong' });
    const safeId = arxivId.replace(/[^A-Za-z0-9.-]+/g, '-');
    const key = `${prefix}uploads/papers/${crypto.randomUUID()}-${safeId}.pdf`;
    await store.set(key, data);
    const now = Date.now();
    const title = String(body.title || `arXiv ${arxivId}`).slice(0, 240);
    const item = { id: crypto.randomUUID(), storage_key: key, file_id: key, filename: `${safeId}.pdf`, title, mime_type: 'application/pdf', kind: 'paper', is_paper: true, arxiv_id: isArxiv ? arxivId : '', source_url: isArxiv ? `https://arxiv.org/abs/${arxivId}` : directPdf, page_count: 0, preview: '', content_url: `/files?key=${encodeURIComponent(key)}`, created_at: now, last_opened_at: now };
    const items = await loadIndex(store, indexKey);
    await store.set(indexKey, JSON.stringify([item, ...items.filter((candidate) => isArxiv ? candidate.arxiv_id !== arxivId : candidate.source_url !== directPdf)].slice(0, 500)));
    return json({ file_id: key, filename: item.filename, title, arxiv_id: arxivId, total_chars: 0, preview: '', content_url: item.content_url });
  } catch (error) { return json({ error: `论文下载失败：${error.message}` }, 502); }
}
