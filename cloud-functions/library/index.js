import { getStore } from '@edgeone/pages-blob';
import { currentUser, tenantPrefix } from '../../auth/current-user.js';

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json; charset=utf-8' } });
}

async function loadJson(store, key, fallback) {
  const raw = await store.get(key, { type: 'arrayBuffer' });
  if (!raw) return fallback;
  try { return JSON.parse(new TextDecoder().decode(raw)); }
  catch { return fallback; }
}

async function saveJson(store, key, value) { await store.set(key, JSON.stringify(value)); }

function inferredFolderName(item) {
  if (item.is_paper || item.kind === 'paper') return '学术论文';
  const text = `${item.title || ''} ${item.filename || ''} ${item.preview || ''}`.toLowerCase();
  if (/合同|协议|contract|agreement/.test(text)) return '合同与协议';
  if (/报告|白皮书|report|white\s*paper/.test(text)) return '报告与白皮书';
  if (/手册|说明书|manual|guide/.test(text)) return '手册与指南';
  if (/书籍|电子书|ebook|book/.test(text)) return '书籍';
  return 'PDF 文档';
}

function ensureFolder(folders, name) {
  let folder = folders.find((item) => item.category === name || item.name === name);
  if (!folder) {
    folder = { id: crypto.randomUUID(), name: name.slice(0, 80), category: name, automatic: true, created_at: Date.now() };
    folders.push(folder);
  }
  return folder;
}

async function loadState(store, keys) {
  const items = await loadJson(store, keys.index, []);
  const folders = await loadJson(store, keys.folders, []);
  const settings = { auto_organize: true, ...await loadJson(store, keys.settings, {}) };
  let changed = false;
  if (settings.auto_organize) {
    for (const item of items) {
      if (!item.folder_id) {
        item.folder_id = ensureFolder(folders, inferredFolderName(item)).id;
        changed = true;
      }
    }
  }
  if (changed) {
    await Promise.all([saveJson(store, keys.index, items), saveJson(store, keys.folders, folders)]);
  }
  return { items, folders, settings };
}

export async function onRequest(context) {
  const { request, env } = context;
  let user;
  try { user = await currentUser(request, env); } catch { return json({ error: 'Unauthorized' }, 401); }
  const prefix = tenantPrefix(user, env);
  const keys = {
    index: `${prefix}library/index.json`,
    folders: `${prefix}library/folders.json`,
    settings: `${prefix}library/settings.json`,
  };
  const store = getStore({ name: 'yuanbao-files', consistency: 'strong' });

  if (request.method === 'GET') {
    const state = await loadState(store, keys);
    state.items.sort((a, b) => Number(b.last_opened_at || b.created_at) - Number(a.last_opened_at || a.created_at));
    return json(state);
  }

  if (request.method === 'POST') {
    const body = await request.json();
    const operation = String(body.operation || 'register');
    const { items, folders, settings } = await loadState(store, keys);

    if (operation === 'settings') {
      settings.auto_organize = body.auto_organize !== false;
      await saveJson(store, keys.settings, settings);
      return json({ settings });
    }
    if (operation === 'create_folder') {
      const name = String(body.name || '').trim().slice(0, 80);
      if (!name) return json({ error: '文件夹名称不能为空' }, 400);
      const folder = folders.find((item) => item.name === name) || { id: crypto.randomUUID(), name, automatic: false, created_at: Date.now() };
      if (!folders.some((item) => item.id === folder.id)) folders.push(folder);
      await saveJson(store, keys.folders, folders);
      return json({ folder, folders });
    }
    if (operation === 'rename_folder') {
      const folder = folders.find((item) => item.id === body.folder_id);
      const name = String(body.name || '').trim().slice(0, 80);
      if (!folder || !name) return json({ error: '文件夹不存在或名称为空' }, 400);
      folder.name = name;
      folder.automatic = false;
      await saveJson(store, keys.folders, folders);
      return json({ folder, folders });
    }
    if (operation === 'move_item') {
      const item = items.find((candidate) => candidate.id === body.item_id);
      if (!item) return json({ error: '阅读项目不存在' }, 404);
      if (body.folder_id && !folders.some((folder) => folder.id === body.folder_id)) return json({ error: '文件夹不存在' }, 404);
      item.folder_id = String(body.folder_id || '');
      await saveJson(store, keys.index, items);
      return json({ item });
    }
    if (operation === 'touch') {
      const item = items.find((candidate) => candidate.id === body.id);
      if (!item) return json({ error: '阅读项目不存在' }, 404);
      item.last_opened_at = Date.now();
      await saveJson(store, keys.index, items);
      return json({ item });
    }

    const storageKey = String(body.storage_key || '');
    if (!storageKey.startsWith(`${prefix}uploads/`)) return json({ error: '无效文档标识' }, 400);
    const existing = items.find((candidate) => candidate.storage_key === storageKey);
    const now = Date.now();
    const item = {
      id: existing?.id || crypto.randomUUID(), storage_key: storageKey, file_id: storageKey,
      filename: String(body.filename || 'document.pdf').slice(0, 180),
      title: String(body.title || body.filename || '未命名文档').slice(0, 240),
      mime_type: String(body.mime_type || 'application/pdf'), kind: body.is_paper ? 'paper' : 'pdf',
      is_paper: Boolean(body.is_paper), arxiv_id: String(body.arxiv_id || '').slice(0, 80),
      page_count: Math.max(0, Number(body.page_count || 0)), preview: String(body.preview || '').slice(0, 1200),
      content_url: `/files?key=${encodeURIComponent(storageKey)}`,
      folder_id: String(body.folder_id || existing?.folder_id || ''),
      created_at: existing?.created_at || now, last_opened_at: now,
    };
    if (!item.folder_id && settings.auto_organize) item.folder_id = ensureFolder(folders, inferredFolderName(item)).id;
    const next = [item, ...items.filter((candidate) => candidate.id !== item.id && candidate.storage_key !== storageKey)];
    await Promise.all([saveJson(store, keys.index, next.slice(0, 500)), saveJson(store, keys.folders, folders)]);
    return json({ item });
  }

  if (request.method === 'DELETE') {
    const url = new URL(request.url);
    const id = url.searchParams.get('id') || '';
    const folderId = url.searchParams.get('folder_id') || '';
    const { items, folders } = await loadState(store, keys);
    if (folderId) {
      await Promise.all([
        saveJson(store, keys.folders, folders.filter((folder) => folder.id !== folderId)),
        saveJson(store, keys.index, items.map((item) => item.folder_id === folderId ? { ...item, folder_id: '' } : item)),
      ]);
    } else {
      await saveJson(store, keys.index, items.filter((item) => item.id !== id));
    }
    return json({ ok: true });
  }
  return json({ error: 'Method not allowed' }, 405);
}
