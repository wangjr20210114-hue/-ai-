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
  assert.match(chat, /write_chat_run\(\s*ctx\.store/);
  assert.match(messages, /langgraph_checkpointer\.aget_tuple/);
  assert.match(messages, /read_chat_run\(ctx\.store/);
  assert.match(files, /@edgeone\/pages-blob/);
  assert.match(config, /"schedules"/);
  const makersConfig = JSON.parse(config);
  assert.equal(makersConfig.schedules[0].cron, '0 8 * * *');
  assert.equal(makersConfig.schedules[0].timezone, 'Asia/Shanghai');
  assert.doesNotMatch(chat + messages, /sqlite|FastAPI|websocket/i);
  assert.doesNotMatch(chat + messages, /yuanbao_chat_runs_v1|chat_runs/);
});

test('identity follows the official Makers auth architecture', async () => {
  const [database, login, currentUser, agentAuth, manifest, schema] = await Promise.all([
    read('cloud-functions/_db.js'),
    read('cloud-functions/auth/login/index.js'),
    read('auth/current-user.js'),
    read('agents/_shared/auth.py'),
    read('package.json'),
    read('db/001_users.sql'),
  ]);
  assert.match(database, /@neondatabase\/serverless/);
  assert.match(login, /bcryptjs/);
  assert.match(login, /serializeSession/);
  assert.match(currentUser, /requireAuth/);
  assert.match(agentAuth, /verify_jwt/);
  assert.match(manifest, /@neondatabase\/serverless/);
  assert.match(schema, /roles JSONB NOT NULL/);
  assert.match(schema, /connector_token_hash/);
  assert.doesNotMatch(database + login, /PBKDF2|deriveBits|auth\/users|auth\/rate/);
});

test('release gates execute the Makers production chain', async () => {
  const [workflow, requirements] = await Promise.all([
    read('.github/workflows/ci.yml'),
    read('requirements.txt'),
  ]);
  assert.match(workflow, /unittest discover -s agents\/_tests/);
  assert.match(workflow, /npm test/);
  assert.match(workflow, /--mode edgeone/);
  assert.doesNotMatch(workflow, /working-directory: backend|import main/);
  assert.doesNotMatch(requirements, />=|~=/);
});

test('static acceptance site covers every release capability with executable details', async () => {
  const [rawCases, html, app, procedures, config] = await Promise.all([
    read('frontend/public/test-cases/cases.json'),
    read('frontend/public/test-cases/index.html'),
    read('frontend/public/test-cases/app.js'),
    read('frontend/public/test-cases/procedures.js'),
    read('edgeone.json'),
  ]);
  const cases = JSON.parse(rawCases);
  assert.ok(cases.length >= 60, `expected a full acceptance matrix, got ${cases.length}`);
  assert.equal(new Set(cases.map((item) => item.id)).size, cases.length);
  for (const item of cases) {
    assert.match(item.id, /^[A-Z]+-\d{2}$/);
    assert.ok(item.module && item.title && item.scope && item.implementation);
    for (const field of ['preconditions', 'data', 'steps', 'expected', 'evidence']) {
      assert.ok(Array.isArray(item[field]) && item[field].length, `${item.id}.${field} is required`);
    }
    if (item.implementation === 'not-implemented') assert.equal(item.releaseBlocker, false);
  }
  const roleRegression = cases.find((item) => item.id === 'CORE-04');
  assert.ok(roleRegression.releaseBlocker);
  assert.match(JSON.stringify(roleRegression), /最近AI有什么新进展/);
  assert.match(JSON.stringify(roleRegression), /error='role'/);
  assert.match(html, /生产发布门禁/);
  assert.match(html, /procedures\.js/);
  assert.match(app, /localStorage/);
  assert.match(app, /导出验收记录|exportResults/);
  assert.match(app, /procedure-table/);
  const authoredIds = [...procedures.matchAll(/^\s*'([A-Z]+-\d{2})': \[/gm)].map((match) => match[1]);
  assert.deepEqual(new Set(authoredIds), new Set(cases.map((item) => item.id)));
  assert.match(procedures, /具体怎么操作|点击|输入/);
  assert.match(procedures, /expected/);
  const acceptanceCopy = rawCases + procedures;
  assert.match(acceptanceCopy, /Request conditions\/请求条件/);
  assert.match(acceptanceCopy, /Block request\/屏蔽请求/);
  assert.match(acceptanceCopy, /\(blocked:devtools\)/);
  assert.match(acceptanceCopy, /Enable blocking and throttling/);
  assert.doesNotMatch(acceptanceCopy, /Network request blocking|Enable network request blocking|\*\/messages\*|\*\/rich_search\*/i);
  assert.deepEqual(
    JSON.parse(config).rewrites.filter((item) => item.source.startsWith('/test-cases')),
    [
      { source: '/test-cases', destination: '/test-cases-entry.html' },
      { source: '/test-cases/', destination: '/test-cases-entry.html' },
    ],
  );
});

test('reported acceptance regressions keep explicit implementation guards', async () => {
  const [files, library, readerClient, chatError, chatTools, chatGraph, workspace] = await Promise.all([
    read('cloud-functions/files/index.js'),
    read('cloud-functions/library/index.js'),
    read('frontend/src/services/paperApi.ts'),
    read('frontend/src/services/chatError.ts'),
    read('agents/chat/_ui_tools.py'),
    read('agents/chat/_graph.py'),
    read('agents/workspace/index.py'),
  ]);
  assert.match(files, /image\/png/);
  assert.match(library, /manual_folder/);
  assert.match(readerClient, /makersConversationHeaders\(getOrCreateConversationId\(\)\)/);
  assert.match(chatError, /failed to fetch/i);
  assert.match(chatTools, /initial_visual_references/);
  assert.match(chatGraph, /handle_tool_errors=TOOL_FAILURE_MESSAGE/);
  assert.match(chatGraph, /工具暂时没有完成/);
  assert.match(workspace, /collect_schedule_signals/);
});

test('Tencent Meeting is optional and never restores a FastAPI bridge', async () => {
  const [provider, tools, envExample] = await Promise.all([
    read('agents/_shared/side_effects.py'),
    read('agents/chat/_ui_tools.py'),
    read('.env.example'),
  ]);
  assert.match(provider, /https:\/\/api\.meeting\.qq\.com\/v1\/meetings/);
  assert.match(provider, /X-TC-Signature/);
  assert.match(envExample, /TENCENT_MEETING_SECRET_ID/);
  assert.match(tools, /if not meeting_ready/);
  assert.doesNotMatch(provider + envExample, /MEETING_BRIDGE|shutil\.which\("tmeet"\)|create_subprocess_exec/);
});

test('legacy data migration terminates in Makers-managed stores', async () => {
  const [exporter, importer, endpoint] = await Promise.all([
    read('tools/export_sqlite.py'),
    read('agents/_shared/legacy_migration.py'),
    read('agents/migration/index.py'),
  ]);
  assert.match(exporter, /mode=ro/);
  assert.match(importer, /append_message/);
  assert.match(importer, /load_user_workspace/);
  assert.match(importer, /load_proactive_state/);
  assert.match(importer, /load_intelligence_state/);
  assert.match(endpoint, /LEGACY_IMPORT_SECRET/);
  assert.match(endpoint, /require_user/);
  assert.doesNotMatch(importer, /import sqlite|from fastapi|import aiosqlite/i);
});

test('runtime does not reimplement generic tracing, queue or cron services', async () => {
  const [system, tick, proactive] = await Promise.all([
    read('agents/system_internal/index.py'),
    read('cloud-functions/proactive-tick/index.js'),
    read('agents/_shared/proactive.py'),
  ]);
  assert.match(tick, /onlyIfNew/);
  assert.match(system, /ctx\.store\.langgraph_store/);
  assert.match(system, /notification_statuses/);
  assert.match(system, /["']schedule["']:\s*["']0 8 \* \* \*["']/);
  assert.doesNotMatch(system, /["']schedule["']:\s*["']0 \* \* \* \*["']/);
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
    read('frontend/src/components/chat/MessageBubble.tsx'),
    read('frontend/src/components/travel/TravelPlanCard.tsx'),
    read('frontend/src/components/travel/RouteMap.tsx'),
    read('frontend/vite.config.ts'),
  ]);
  const active = sources.join('\n');
  assert.doesNotMatch(
    active,
    /["'`]\/api\/|useWebSocket|new WebSocket|X-Agent-Token|127\.0\.0\.1:8000|target:\s*["'`]ws/,
  );
  assert.match(active, /useSSEChat/);
  assert.match(active, /AuthGate/);
  const chatClient = await read('frontend/src/hooks/useSSEChat.ts');
  const stopRequest = chatClient.match(/fetch\(withEdgeOneAuth\('\/stop'\)[\s\S]*?body: JSON\.stringify/);
  assert.ok(stopRequest);
  assert.doesNotMatch(stopRequest[0], /makersConversationHeaders/);
});
