import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const read = (path) => readFile(resolve(root, path), 'utf8');

test('conversation, state, object and schedule infrastructure reuse EdgeOne Makers', async () => {
  const [chat, messages, files, config] = await Promise.all([
    read('agents/chat/index.py'),
    read('agents/messages/index.py'),
    read('cloud-functions/files/index.js'),
    read('edgeone.json'),
  ]);
  assert.match(chat, /ctx\.store\.langgraph_checkpointer/);
  assert.match(chat, /ctx\.store\.langgraph_store/);
  assert.match(messages, /langgraph_checkpointer\.aget_tuple/);
  assert.match(files, /@edgeone\/pages-blob/);
  assert.match(config, /"schedules"/);
  assert.doesNotMatch(chat + messages, /sqlite|FastAPI|websocket/i);
});

test('identity follows the official Makers auth architecture', async () => {
  const [database, login, middleware, manifest] = await Promise.all([
    read('cloud-functions/_db.js'),
    read('cloud-functions/auth/login/index.js'),
    read('middleware.js'),
    read('package.json'),
  ]);
  assert.match(database, /@neondatabase\/serverless/);
  assert.match(login, /bcryptjs/);
  assert.match(login, /serializeSession/);
  assert.match(middleware, /verifyToken/);
  assert.match(manifest, /@neondatabase\/serverless/);
  assert.doesNotMatch(database + login, /PBKDF2|deriveBits|auth\/users|auth\/rate/);
});

test('runtime does not reimplement generic tracing, queue or cron services', async () => {
  const [system, tick, proactive] = await Promise.all([
    read('agents/system/index.py'),
    read('cloud-functions/proactive-tick/index.js'),
    read('agents/shared/proactive.py'),
  ]);
  assert.match(tick, /onlyIfNew/);
  assert.match(system, /notification_statuses/);
  assert.match(proactive, /Policy|policy|notification/i);
  assert.doesNotMatch(system + tick, /OPS_ALERT_WEBHOOK|PROACTIVE_OPS_WEBHOOK|Sentry|OpenTelemetry/);
});

test('production frontend has no active FastAPI or WebSocket transport fallback', async () => {
  const sources = await Promise.all([
    read('frontend/src/App.tsx'),
    read('frontend/src/main.tsx'),
    read('frontend/src/services/auth.ts'),
    read('frontend/src/services/paperApi.ts'),
    read('frontend/src/components/chat/InputBar.tsx'),
  ]);
  const active = sources.join('\n');
  assert.doesNotMatch(active, /\/api\/|useWebSocket|new WebSocket|X-Agent-Token/);
  assert.match(active, /useSSEChat/);
  assert.match(active, /AuthGate/);
});
