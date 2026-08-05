import { readFileSync } from 'node:fs';
import { extname } from 'node:path';

import {
  createSmokeClient,
  createSmokeConversationId,
} from './smoke-session.mjs';

const baseUrl = String(
  process.env.FLORIS_SMOKE_BASE_URL || 'https://floris.jlutx.com',
).replace(/\/+$/, '');
const authQuery = String(process.env.FLORIS_SMOKE_AUTH_QUERY || '').replace(/^\?/, '');
const smoke = await createSmokeClient({ baseUrl, authQuery });
const label = String(process.env.FLORIS_TIMELINE_LABEL || 'skill')
  .toLowerCase()
  .replace(/[^a-z0-9_-]+/g, '-')
  .slice(0, 32);
const message = String(process.env.FLORIS_TIMELINE_MESSAGE || '').trim();
if (!message) throw new Error('FLORIS_TIMELINE_MESSAGE is required');

const conversationId = createSmokeConversationId(`skill-${label}`);
const startedAt = performance.now();
const events = [];

function elapsedMs() {
  return Math.round(performance.now() - startedAt);
}

function toolName(event) {
  return event?.payload?.name
    || event?.payload?.tool_name
    || event?.name
    || '';
}

function record(frame) {
  const payload = frame.split(/\r?\n/)
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trim())
    .join('\n');
  if (!payload || payload === '[DONE]') return;
  try {
    const event = JSON.parse(payload);
    const row = {
      elapsed_ms: elapsedMs(),
      type: event?.type || '',
      tool: toolName(event),
    };
    if (row.type === 'error_message') {
      row.message = String(
        event?.message
        || event?.content
        || event?.error
        || event?.payload?.message
        || '',
      ).slice(0, 500);
    }
    if (
      row.type === 'ai_response'
      && events.some((item) => item.type === 'ai_response')
    ) return;
    events.push(row);
    process.stderr.write(`${JSON.stringify(row)}\n`);
  } catch {
    // Ignore transport heartbeats that are not JSON events.
  }
}

function referenceImages() {
  if (process.env.FLORIS_TIMELINE_REFERENCE_PIXEL === '1') {
    // One opaque red pixel: enough to exercise the reference-image provider
    // path without downloading or committing a test asset.
    return [
      'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z2S8AAAAASUVORK5CYII=',
    ];
  }
  const path = String(process.env.FLORIS_TIMELINE_REFERENCE_PATH || '').trim();
  if (!path) return [];
  const extension = extname(path).toLowerCase();
  const mime = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.webp': 'image/webp',
  }[extension];
  if (!mime) throw new Error(`Unsupported reference image extension: ${extension}`);
  return [`data:${mime};base64,${readFileSync(path).toString('base64')}`];
}

const headers = {
  'Content-Type': 'application/json',
  'makers-conversation-id': conversationId,
};
const response = await smoke.fetch('/chat', {
  method: 'POST',
  headers,
  body: JSON.stringify({
    message,
    response_language: 'zh-CN',
    reference_images: referenceImages(),
  }),
});
if (!response.ok || !response.body) {
  throw new Error(`HTTP ${response.status}: ${(await response.text()).slice(0, 500)}`);
}

const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = '';
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  const frames = buffer.split(/\r?\n\r?\n/);
  buffer = frames.pop() || '';
  for (const frame of frames) record(frame);
}
buffer += decoder.decode();
if (buffer.trim()) record(buffer);

let persisted = {};
try {
  const messagesResponse = await smoke.fetch('/messages', {
    method: 'POST',
    headers,
    body: JSON.stringify({ conversation_id: conversationId }),
  });
  if (messagesResponse.ok) {
    const body = await messagesResponse.json();
    const assistantMessages = (body.messages || []).filter((item) => item?.role === 'ai');
    const actions = assistantMessages.flatMap((item) => item?.workspaceActions || []);
    persisted = {
      assistant_message_count: assistantMessages.length,
      final_content_chars: String(assistantMessages.at(-1)?.content || '').length,
      action_count: actions.length,
      action_kinds: actions.map((action) => action?.kind || ''),
      action_statuses: actions.map((action) => action?.status || ''),
    };
  }
} catch {
  persisted = { messages_lookup_failed: true };
}

process.stdout.write(`${JSON.stringify({
  label,
  base_url: baseUrl,
  auth: smoke.auth,
  conversation_id: conversationId,
  total_ms: elapsedMs(),
  events,
  persisted,
}, null, 2)}\n`);
