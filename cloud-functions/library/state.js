export const LIBRARY_DATA_GENERATION = 'v7_20260724_clear';

export function libraryKeys(prefix) {
  return {
    index: `${prefix}library/${LIBRARY_DATA_GENERATION}/index.json`,
    folders: `${prefix}library/${LIBRARY_DATA_GENERATION}/folders.json`,
    settings: `${prefix}library/${LIBRARY_DATA_GENERATION}/settings.json`,
  };
}

export async function loadJson(store, key, fallback) {
  const raw = await store.get(key, { type: 'arrayBuffer' });
  if (!raw) return fallback;
  try { return JSON.parse(new TextDecoder().decode(raw)); }
  catch { return fallback; }
}

export async function saveJson(store, key, value) {
  await store.set(key, JSON.stringify(value));
}

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
    folder = {
      id: crypto.randomUUID(), name: name.slice(0, 80), category: name,
      automatic: true, created_at: Date.now(),
    };
    folders.push(folder);
  }
  return folder;
}

export async function loadLibraryState(store, keys) {
  const items = await loadJson(store, keys.index, []);
  const folders = await loadJson(store, keys.folders, []);
  const settings = { auto_organize: true, ...await loadJson(store, keys.settings, {}) };
  let changed = false;
  if (settings.auto_organize) {
    for (const item of items) {
      if (!item.folder_id && !item.manual_folder) {
        item.folder_id = ensureFolder(folders, inferredFolderName(item)).id;
        changed = true;
      }
    }
  }
  if (changed) {
    await Promise.all([
      saveJson(store, keys.index, items),
      saveJson(store, keys.folders, folders),
    ]);
  }
  return { items, folders, settings };
}

export async function persistLibraryItem(store, keys, item, state) {
  const current = state || await loadLibraryState(store, keys);
  if (!item.folder_id && current.settings.auto_organize && !item.manual_folder) {
    item.folder_id = ensureFolder(current.folders, inferredFolderName(item)).id;
  }
  const next = [
    item,
    ...current.items.filter((candidate) => (
      candidate.id !== item.id && candidate.storage_key !== item.storage_key
    )),
  ].slice(0, 500);
  await Promise.all([
    saveJson(store, keys.index, next),
    saveJson(store, keys.folders, current.folders),
  ]);
  return item;
}

export const __test = { ensureFolder, inferredFolderName };
