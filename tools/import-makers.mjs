#!/usr/bin/env node
/** Import an exported bundle through Makers APIs and the official Blob SDK. */

import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { resolve, basename } from 'node:path';
import pagesBlob from '@edgeone/pages-blob';

const { getStore } = pagesBlob;

function argumentsMap(values) {
  const options = {};
  for (let index = 0; index < values.length; index += 1) {
    const value = values[index];
    if (!value.startsWith('--')) continue;
    const [rawKey, inline] = value.slice(2).split('=', 2);
    if (inline !== undefined) options[rawKey] = inline;
    else if (values[index + 1] && !values[index + 1].startsWith('--')) options[rawKey] = values[++index];
    else options[rawKey] = true;
  }
  return options;
}

async function jsonFile(path) {
  return JSON.parse(await readFile(path, 'utf8'));
}

async function ndjson(path) {
  const text = await readFile(path, 'utf8');
  return text.split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
}

function sha256(value) {
  return createHash('sha256').update(value).digest('hex');
}

async function migrationRequest(options, payload) {
  const response = await fetch(new URL('/migration', options.baseUrl), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'makers-conversation-id': 'migration-control',
      'x-yuanbao-migration-secret': options.secret,
    },
    body: JSON.stringify(payload),
  });
  const result = await response.json().catch(() => ({ error: `HTTP ${response.status}` }));
  if (!response.ok) throw new Error(`Makers migration failed (${response.status}): ${JSON.stringify(result)}`);
  return result;
}

function safeSegment(value, fallback = 'file') {
  const normalized = String(value || '').normalize('NFKC').replace(/[^\p{L}\p{N}._-]+/gu, '-').replace(/^-+|-+$/g, '');
  return (normalized || fallback).slice(0, 120);
}

async function importFiles(options, manifest, files) {
  if (!files.length) return { imported: 0, skipped: 0 };
  if (!options.projectId || !options.apiToken) {
    return { imported: 0, skipped: files.length, reason: 'Blob upload requires --project-id and --api-token' };
  }
  const store = getStore({ name: 'yuanbao-files', projectId: options.projectId, token: options.apiToken, consistency: 'strong' });
  const indexKey = 'library/index.json';
  const existing = await store.get(indexKey, { type: 'json', consistency: 'strong' }).catch(() => []);
  const library = Array.isArray(existing) ? existing : [];
  let imported = 0;
  let skipped = 0;
  for (const item of files) {
    if (!item.exported_path) { skipped += 1; continue; }
    const localPath = resolve(options.bundle, item.exported_path);
    const bytes = await readFile(localPath);
    const digest = sha256(bytes);
    if (item.actual_sha256 && digest !== item.actual_sha256) throw new Error(`File hash mismatch: ${item.exported_path}`);
    const filename = safeSegment(item.original_name || basename(localPath));
    const storageKey = `uploads/migration/${manifest.export_id}/${safeSegment(item.id, digest.slice(0, 16))}-${filename}`;
    const contentType = String(item.mime_type || (filename.toLowerCase().endsWith('.pdf') ? 'application/pdf' : 'application/octet-stream'));
    const upload = await store.createUploadUrl(storageKey, { expireSeconds: 600, contentType });
    const response = await fetch(upload.url, { method: 'PUT', headers: { 'Content-Type': contentType }, body: bytes });
    if (!response.ok) throw new Error(`Blob upload failed (${response.status}): ${filename}`);
    const now = Date.now();
    const libraryItem = {
      id: String(item.id || `legacy-${digest.slice(0, 24)}`),
      storage_key: storageKey,
      file_id: storageKey,
      filename,
      title: String(item.original_name || filename).slice(0, 240),
      mime_type: contentType,
      kind: item.arxiv_id ? 'paper' : 'pdf',
      is_paper: Boolean(item.arxiv_id),
      arxiv_id: String(item.arxiv_id || ''),
      page_count: Number(item.page_count || 0),
      preview: String(item.extracted_text || '').slice(0, 1200),
      content_url: `/files?key=${encodeURIComponent(storageKey)}`,
      folder_id: '',
      created_at: Number(item.created_at || now),
      last_opened_at: Number(item.created_at || now),
      migration_export_id: manifest.export_id,
      legacy_sha256: digest,
    };
    const index = library.findIndex((candidate) => candidate.storage_key === storageKey || candidate.id === libraryItem.id);
    if (index >= 0) library[index] = libraryItem;
    else library.push(libraryItem);
    imported += 1;
  }
  await store.setJSON(indexKey, library.slice(-500));
  return { imported, skipped };
}

async function main() {
  const args = argumentsMap(process.argv.slice(2));
  if (!args.bundle || !args['base-url'] || !args.secret) {
    throw new Error('Usage: node tools/import-makers.mjs --bundle DIR --base-url PREVIEW_URL --secret SECRET [--project-id ID --api-token TOKEN]');
  }
  const options = {
    bundle: resolve(String(args.bundle)),
    baseUrl: String(args['base-url']),
    secret: String(args.secret),
    projectId: args['project-id'] ? String(args['project-id']) : '',
    apiToken: args['api-token'] ? String(args['api-token']) : '',
    userId: String(args['user-id'] || 'local-user'),
  };
  if (options.secret.length < 32) throw new Error('--secret must contain at least 32 characters');
  const manifest = await jsonFile(resolve(options.bundle, 'manifest.json'));
  const [states, conversations, messages, files] = await Promise.all([
    ndjson(resolve(options.bundle, 'states.ndjson')),
    ndjson(resolve(options.bundle, 'conversations.ndjson')),
    ndjson(resolve(options.bundle, 'messages.ndjson')),
    ndjson(resolve(options.bundle, 'files.ndjson')),
  ]);
  if (manifest.schema_version !== 1 || !/^sqlite_[0-9a-f]{24}$/.test(manifest.export_id)) throw new Error('Unsupported migration bundle');
  const state = states.find((item) => item.user_id === options.userId) || states.find((item) => item.user_id === 'local-user');
  const stateResult = state
    ? await migrationRequest(options, { operation: 'import_state', export_id: manifest.export_id, state })
    : { skipped: true };
  const conversationResults = [];
  for (const conversation of conversations) {
    const conversationId = String(conversation.id || '');
    const items = messages.filter((message) => String(message.conversation_id || '') === conversationId);
    for (let index = 0; index < items.length; index += 50) {
      conversationResults.push(await migrationRequest(options, {
        operation: 'import_messages', export_id: manifest.export_id,
        conversation_id: conversationId, title: String(conversation.title || '历史会话'),
        messages: items.slice(index, index + 50),
      }));
    }
  }
  const fileResult = await importFiles(options, manifest, files);
  console.log(JSON.stringify({
    ok: true,
    export_id: manifest.export_id,
    state: stateResult,
    conversations: conversationResults.length,
    messages_imported: conversationResults.reduce((sum, item) => sum + Number(item.imported || 0), 0),
    files: fileResult,
  }));
}

main().catch((error) => {
  console.error(String(error?.message || error));
  process.exitCode = 1;
});
