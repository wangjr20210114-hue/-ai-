import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const read = (path) => readFile(resolve(root, path), 'utf8');

test('conversation, state, object and schedule infrastructure reuse EdgeOne Makers', async () => {
  const [chat, messages, conversationRoute, conversationIndex, files, config] = await Promise.all([
    read('agents/_application/chat/turn_service.py'),
    read('agents/_controllers/messages_controller.py'),
    read('cloud-functions/conversations/index.js'),
    read('cloud-functions/conversation-index.js'),
    read('cloud-functions/files/index.js'),
    read('edgeone.json'),
  ]);
  assert.match(chat, /ctx\.store\.langgraph_checkpointer/);
  assert.match(chat, /ctx\.store\.langgraph_store/);
  assert.match(chat, /write_chat_run\(\s*ctx\.store/);
  assert.match(messages, /langgraph_checkpointer\.aget_tuple/);
  assert.match(messages, /read_chat_run\(ctx\.store/);
  assert.match(conversationRoute, /@edgeone\/pages-blob/);
  assert.match(conversationRoute + conversationIndex, /conversation-index\/v1/);
  assert.match(files, /@edgeone\/pages-blob/);
  assert.match(config, /"schedules"/);
  const makersConfig = JSON.parse(config);
  assert.equal(makersConfig.schedules[0].cron, '0 8 * * *');
  assert.equal(makersConfig.schedules[0].timezone, 'Asia/Shanghai');
  assert.equal(makersConfig.schedules[0].path, '/proactive-tick');
  assert.equal(makersConfig.cloudFunctions.nodejs.maxDuration, 120);
  assert.doesNotMatch(chat + messages + conversationRoute + conversationIndex, /sqlite|FastAPI|websocket/i);
  assert.doesNotMatch(chat + messages, /yuanbao_chat_runs_v1|chat_runs/);
});

test('runtime is pure multi-user with signed sessions and tenant-scoped storage', async () => {
  const [
    currentUser,
    session,
    agentAuth,
    workspace,
    proactive,
    intelligence,
    frontendState,
    manifest,
    migration,
  ] = await Promise.all([
    read('auth/current-user.js'),
    read('auth/session.js'),
    read('agents/_infrastructure/makers/identity.py'),
    read('agents/_application/workspace/service.py'),
    read('agents/_application/proactive/service.py'),
    read('agents/_application/intelligence/service.py'),
    read('frontend/src/store/appState.ts'),
    read('package.json'),
    read('db/migrations/001_identity_and_entitlements.sql'),
  ]);
  const runtimeIdentitySources = [
    currentUser,
    session,
    agentAuth,
    workspace,
    proactive,
    intelligence,
    frontendState,
  ].join('\n');
  assert.match(currentUser + session + agentAuth, /JWT_SECRET/);
  assert.match(session, /tenantPrefix/);
  assert.match(manifest, /@neondatabase\/serverless/);
  assert.match(migration, /ROW LEVEL SECURITY/);
  assert.match(migration, /FORCE ROW LEVEL SECURITY/);
  assert.doesNotMatch(
    runtimeIdentitySources,
    /AUTH_MODE|local-user|USER_WORKSPACE_ID|single_user|fixed owner/i,
  );
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
  const acceptanceById = new Map(cases.map((item) => [item.id, item]));
  for (const id of ['TRAVEL-13', 'CORE-10', 'READ-08', 'PRO-12']) {
    assert.equal(acceptanceById.get(id)?.implementation, 'implemented', `${id} must be executable`);
    assert.equal(acceptanceById.get(id)?.releaseBlocker, true, `${id} must gate releases`);
  }
  const groupedRoute = JSON.stringify(acceptanceById.get('TRAVEL-13'));
  assert.match(groupedRoute, /一次展示全部未解决字段|一张卡片组/);
  assert.match(groupedRoute, /只点击一次确认并继续|一次提交/);
  assert.match(groupedRoute, /刷新|Makers 会话恢复/);
  const ordinalMemory = JSON.stringify(acceptanceById.get('CORE-10'));
  assert.match(ordinalMemory, /第四个/);
  assert.match(ordinalMemory, /不把“第四个”交给地点服务/);
  assert.match(ordinalMemory, /一次语义计划|未启动不相关 Skill/);
  const verifiedPaper = JSON.stringify(acceptanceById.get('READ-08'));
  assert.match(verifiedPaper, /复旦大学彭鑫/);
  assert.match(verifiedPaper, /模型记忆输出只是候选/);
  assert.match(verifiedPaper, /官方 arXiv ID、作者和时间核验/);
  const proactiveWindow = JSON.stringify(acceptanceById.get('PRO-12'));
  assert.match(proactiveWindow, /先来先服务/);
  assert.match(proactiveWindow, /超过 10 条|第 11 条/);
  assert.match(proactiveWindow, /五分钟|每五分钟/);
  for (const id of ['TRAVEL-05', 'TRAVEL-09']) {
    const start = procedures.indexOf(`  '${id}': [`);
    const end = procedures.indexOf("\n  '", start + 1);
    const procedure = procedures.slice(start, end);
    assert.match(procedure, /确认并继续/);
    assert.match(procedure, /自动续跑/);
    assert.match(procedure, /不新增用户气泡/);
  }
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
  const [files, library, readerClient, chatError, chatTools, chatGraph, workspace, messageBubble, clarificationSubmission, capabilityPlan, chatAgent, styles, chatClient, chatTransport] = await Promise.all([
    read('cloud-functions/files/index.js'),
    read('cloud-functions/library/index.js'),
    read('frontend/src/features/papers/model/api.ts'),
    read('frontend/src/services/chatError.ts'),
    read('agents/_infrastructure/skills/builtin_operations.py'),
    read('agents/chat/_graph.py'),
    read('agents/_controllers/workspace_controller.py'),
    read('frontend/src/features/chat/view/renderers/ClarificationCard.tsx'),
    read('frontend/src/components/chat/clarificationSubmission.ts'),
    read('agents/chat/_capability_plan.py'),
    read('agents/_application/chat/turn_service.py'),
    read('frontend/src/styles/reset.css'),
    read('frontend/src/features/chat/model/client.ts'),
    read('frontend/src/features/chat/controller/chatTransport.ts'),
  ]);
  assert.match(files, /image\/png/);
  assert.match(library, /manual_folder/);
  assert.match(readerClient, /makersConversationHeaders\(getOrCreateConversationId\(\)\)/);
  assert.match(chatError, /failed to fetch/i);
  assert.match(chatTools, /initial_visual_references/);
  assert.match(chatGraph, /handle_tool_errors=_tool_failure_message/);
  assert.match(chatGraph, /工具暂时没有完成/);
  assert.match(chatGraph, /isinstance\(exc, ValueError\)/);
  assert.match(workspace, /collect_schedule_signals/);
  const clarificationCard = messageBubble;
  assert.match(clarificationSubmission, /activity: 'clarification_answered'/);
  assert.match(clarificationSubmission, /interaction_mode: 'clarification'/);
  assert.doesNotMatch(clarificationSubmission, /\bclient_message:/);
  assert.match(clarificationCard, /client\.current\.send/);
  assert.doesNotMatch(clarificationCard, /SET_DRAFT/);
  assert.doesNotMatch(capabilityPlan, /def clarification_tool_available/);
  assert.doesNotMatch(chatAgent, /if not clarification_tool_available/);
  assert.match(chatAgent, /product-wide interaction capability/);
  assert.match(chatGraph, /required_or_question_tools/);
  assert.match(styles, /themeDiagonalReveal 280ms/);
  assert.match(chatClient, /operation: 'touch_pointer'/);
  assert.match(chatClient, /yuanbao:conversation-saved/);
  assert.match(chatTransport, /touchConversationIndex\(this\.conversationId/);
  assert.doesNotMatch(styles, /themeDiagonalReveal 1100ms/);
});

test('Tencent Meeting uses only the optional user-connected official MCP Skill', async () => {
  const [provider, tools, envExample, skillsApi, manifest, registry] = await Promise.all([
    read('agents/_infrastructure/providers/side_effects.py'),
    read('agents/_infrastructure/skills/builtin_operations.py'),
    read('.env.example'),
    read('frontend/src/features/settings/model/client.ts'),
    read('agents/skill_packages/tencent-meeting/floris.json'),
    read('agents/_application/skills/registry.py'),
  ]);
  assert.match(provider, /mcp\.meeting\.tencent\.com/);
  assert.match(provider, /X-Tencent-Meeting-Token/);
  assert.match(envExample, /TENCENT_MEETING_TOKEN/);
  assert.doesNotMatch(provider + envExample, /TENCENT_MEETING_SECRET_ID|X-TC-Signature/);
  assert.equal(JSON.parse(manifest).external, true);
  assert.deepEqual(JSON.parse(manifest).provider_env, ['TENCENT_MEETING_TOKEN']);
  assert.deepEqual(JSON.parse(manifest).requires, ['calendar']);
  assert.match(tools, /build_adapter_tools/);
  assert.match(registry, /def skill_is_configured/);
  assert.match(skillsApi, /intelligenceOperation/);
  assert.match(skillsApi, /['"]makers-conversation-id['"]:\s*conversationId/);
  assert.doesNotMatch(skillsApi, /skillsOperation[\s\S]{0,800}authorizedFetch\('\/system(?:_internal)?'/);
  assert.doesNotMatch(provider + envExample, /MEETING_BRIDGE|shutil\.which\("tmeet"\)|create_subprocess_exec/);
});

test('settings and Skills open on lightweight configuration reads', async () => {
  const [settings, skills, skillsController, api, intelligenceController, library, paperApi, input, registry, styles, header] = await Promise.all([
    Promise.all([
      read('frontend/src/features/settings/view/AppSettingsButton.tsx'),
      read('frontend/src/features/settings/controller/useSettingsController.ts'),
      read('frontend/src/features/settings/model/client.ts'),
    ]).then((sources) => sources.join('\n')),
    Promise.all([
      read('frontend/src/features/skills/view/SkillsMarketplaceButton.tsx'),
      read('frontend/src/features/skills/view/SkillsMarketplaceShell.tsx'),
    ]).then((sources) => sources.join('\n')),
    read('frontend/src/features/skills/controller/useSkillMarketplaceController.ts'),
    read('frontend/src/features/skills/model/client.ts'),
    read('agents/_controllers/intelligence_controller.py'),
    read('cloud-functions/library/index.js'),
    read('frontend/src/features/papers/model/api.ts'),
    read('frontend/src/components/chat/InputBar.tsx'),
    read('agents/_application/skills/registry.py'),
    read('frontend/src/features/skills/page.css'),
    read('frontend/src/components/common/Header.tsx'),
  ]);
  const settingsOpenEffects = settings.slice(0, settings.indexOf('const setPreferences'));
  assert.doesNotMatch(settingsOpenEffects, /runProactive\(['"]refresh['"]/);
  assert.match(settings, /runProactive\(['"]refresh['"]/);
  assert.match(settings, /getReadingSettings\(\)/);
  assert.doesNotMatch(settings, /settingsReady|settings-loading-state/);
  assert.match(paperApi, /\/library\?view=settings/);
  assert.match(library, /searchParams\.get\('view'\) === 'settings'/);
  assert.doesNotMatch(skills, /skill-market-skeleton/);
  assert.doesNotMatch(api, /skillsOperation[\s\S]{0,800}system_internal/);
  assert.match(intelligenceController, /public_intelligence_view/);
  assert.match(skillsController, /skillMarketplaceOperation\(conversationId\)/);
  assert.match(skillsController, /setMarketplace\(result\)/);
  assert.doesNotMatch(skills, /skillsCatalog/);
  assert.match(registry, /SKILL\.md/);
  assert.match(registry, /floris\.json/);
  assert.doesNotMatch(registry, /pkgutil\.iter_modules/);
  assert.doesNotMatch(input, /web_search|webSearch|Checkbox/);
  assert.match(skills, /createPortal/);
  assert.match(skills, /document\.body/);
  assert.match(styles, /\.skills-page\s*\{[\s\S]*?z-index:\s*5000/);
  assert.match(header, /openAuthDialog/);
  assert.doesNotMatch(header, /wechatLoginUnavailable|login\.wechat_available/);
  assert.doesNotMatch(header, /aria-disabled=/);
  assert.match(skillsController, /openAuthDialog/);
  assert.doesNotMatch(skillsController, /wechatLoginUnavailable|startWechatLogin/);
  assert.match(skills, /accountIdentity\.auth_type === 'guest'/);
  assert.match(skillsController, /currentAuthSession/);
  assert.match(skillsController, /floris:auth-changed/);
});

test('new multi-user and Skill surfaces follow the layered MVC boundary', async () => {
  const [
    skillRoute,
    middleware,
    api,
    proactiveManifest,
    skillController,
    skillModel,
    skillView,
    marketplaceView,
    marketplaceController,
    marketplaceModel,
  ] = await Promise.all([
    read('agents/skill_marketplace/index.py'),
    read('middleware.js'),
    read('frontend/src/features/skills/model/client.ts'),
    read('agents/skill_packages/proactive-agent/floris.json'),
    read('agents/_controllers/skills_controller.py'),
    read('agents/_models/skill_marketplace.py'),
    read('agents/_views/skill_marketplace.py'),
    Promise.all([
      read('frontend/src/features/skills/view/SkillsMarketplaceButton.tsx'),
      read('frontend/src/features/skills/view/SkillsMarketplaceShell.tsx'),
    ]).then((sources) => sources.join('\n')),
    read('frontend/src/features/skills/controller/useSkillMarketplaceController.ts'),
    read('frontend/src/features/skills/model.ts'),
  ]);
  assert.match(skillRoute, /handle_skills/);
  assert.doesNotMatch(skillRoute, /load_intelligence_state|public_skill_catalog/);
  assert.match(middleware, /\/skill_marketplace\/:path\*/);
  assert.doesNotMatch(middleware, /['"]\/skills\/:path\*/);
  assert.match(api, /requestJson(?:<[^>]+>)?\('\/skill_marketplace'/);
  assert.doesNotMatch(api, /requestJson(?:<[^>]+>)?\('\/skills'/);
  assert.match(proactiveManifest, /agents\._skill_adapters\.proactive_agent/);
  assert.doesNotMatch(proactiveManifest, /agents\.skill_adapters/);
  assert.match(skillController, /decorate_catalog/);
  assert.match(skillController, /marketplace_view/);
  assert.match(skillModel, /def decorate_catalog/);
  assert.doesNotMatch(skillModel, /ctx\.|\bhandler\(|\bResponse\(/);
  assert.match(skillView, /def marketplace_view/);
  assert.match(marketplaceView, /useSkillMarketplaceController/);
  assert.doesNotMatch(marketplaceView, /authorizedFetch|skillMarketplaceOperation/);
  assert.match(marketplaceController, /skillMarketplaceOperation/);
  assert.match(marketplaceModel, /filterMarketplaceSkills/);
});

test('runtime does not reimplement generic tracing, queue or cron services', async () => {
  const [system, tick, proactive, skillRuntime, adapters] = await Promise.all([
    read('agents/_controllers/system_controller.py'),
    read('cloud-functions/proactive-tick/index.js'),
    read('agents/_application/proactive/service.py'),
    read('agents/_application/skills/runtime_ports.py'),
    Promise.all([
      'core',
      'proactive_agent',
      'web_search',
      'vision',
      'image_studio',
      'maps',
      'calendar',
      'paper_reading',
      'tencent_meeting',
    ].map((name) => read(`agents/_skill_adapters/${name}/adapter.py`))).then((values) => values.join('\n')),
  ]);
  assert.match(tick, /@edgeone\/pages-blob/);
  assert.match(tick, /onlyIfNew/);
  assert.match(tick, /store\.delete\(lockKey\)/);
  assert.match(system, /ctx\.store\.langgraph_store/);
  assert.match(system, /notification_statuses/);
  assert.match(system, /["']schedule["']:\s*["']0 8 \* \* \*["']/);
  assert.doesNotMatch(system, /["']schedule["']:\s*["']0 \* \* \* \*["']/);
  assert.match(proactive, /Policy|policy|notification/i);
  assert.match(skillRuntime, /ToolOperationService/);
  assert.doesNotMatch(
    system + tick + skillRuntime + adapters,
    /OPS_ALERT_WEBHOOK|PROACTIVE_OPS_WEBHOOK|Sentry|OpenTelemetry|Redis|BullMQ|Celery|APScheduler|node-cron|sqlite|boto3|new WebSocket/i,
  );
  assert.doesNotMatch(adapters, /pages_blob|get_store|langgraph_checkpointer|langgraph_store/);
});

test('self-service reset only deletes the authenticated Makers namespace', async () => {
  const [agentReset, fileReset, settings, envExample] = await Promise.all([
    read('agents/_controllers/reset_controller.py'),
    Promise.all([
      read('cloud-functions/reset-files/index.js'),
      read('cloud-functions/conversation-index.js'),
    ]).then((sources) => sources.join('\n')),
    Promise.all([
      read('frontend/src/features/settings/view/AppSettingsButton.tsx'),
      read('frontend/src/features/settings/controller/useSettingsController.ts'),
      read('frontend/src/features/settings/model/client.ts'),
    ]).then((sources) => sources.join('\n')),
    read('.env.example'),
  ]);
  assert.match(agentReset, /ctx\.store\.langgraph_store/);
  assert.match(agentReset, /checkpointer\.adelete_thread/);
  assert.match(agentReset, /getattr\(function, "__globals__"/);
  assert.match(agentReset, /globals_map\.setdefault\("asyncio", asyncio\)/);
  assert.match(fileReset, /@edgeone\/pages-blob/);
  assert.match(fileReset, /context\.agent\?\.store/);
  assert.match(fileReset, /listConversations/);
  assert.match(fileReset, /deleteConversation/);
  assert.match(agentReset + fileReset, /DELETE/);
  assert.match(fileReset, /tenantPrefix\(user\)/);
  assert.doesNotMatch(fileReset, /yuanbao-acceptance-shared|yuanbao-auth/);
  assert.doesNotMatch(agentReset + fileReset + envExample, /DATA_CLEAR_PASSWORD/);
  assert.match(settings, /resetApplicationData/);
  assert.doesNotMatch(agentReset + fileReset + settings + envExample, /wangjryyds/);
});

test('production frontend has no active FastAPI or WebSocket transport fallback', async () => {
  const sources = await Promise.all([
    read('frontend/src/app/App.tsx'),
    read('frontend/src/main.tsx'),
    read('frontend/src/services/auth.ts'),
    read('frontend/src/features/papers/model/api.ts'),
    read('frontend/src/components/chat/InputBar.tsx'),
    read('frontend/src/features/chat/view/MessageBubble.tsx'),
    read('frontend/src/features/chat/view/renderers/MessageBubbleView.tsx'),
    read('frontend/src/features/chat/view/renderers/MessagePrimaryRenderer.tsx'),
    read('frontend/src/features/chat/view/renderers/WorkspaceActionRenderer.tsx'),
    read('frontend/src/features/chat/controller/useMessageBubbleController.ts'),
    read('frontend/src/features/maps/view/MakersMap.tsx'),
    read('frontend/vite.config.ts'),
  ]);
  const active = sources.join('\n');
  assert.doesNotMatch(
    active,
    /["'`]\/api\/|useWebSocket|new WebSocket|X-Agent-Token|127\.0\.0\.1:8000|target:\s*["'`]ws/,
  );
  assert.match(active, /useChatController/);
  assert.doesNotMatch(active, /useSSEChat/);
  assert.doesNotMatch(active, /AuthGate|loginAppSession|registerAppSession/);
  const [chatClient, chatModel] = await Promise.all([
    read('frontend/src/features/chat/controller/chatTransport.ts'),
    read('frontend/src/features/chat/model/client.ts'),
  ]);
  assert.match(chatClient, /requestConversationStop\(this\.conversationId/);
  const stopRequest = chatModel.match(
    /export function requestConversationStop[\s\S]*?authorizedFetch\('\/stop'[\s\S]*?body: JSON\.stringify/,
  );
  assert.ok(stopRequest);
  assert.doesNotMatch(stopRequest[0], /makersConversationHeaders/);
  assert.doesNotMatch(
    chatClient,
    /transport_recovering|RECOVERY_DEADLINE|shouldAutoResume|async resume\s*\(/,
    'failed or stopped chat runs must never resume automatically',
  );
  const i18n = await read('frontend/src/i18n.tsx');
  assert.match(chatClient, /translate\('networkGenerationEnded'\)/);
  assert.match(i18n, /不会自动重试/);
  assert.match(active, /t\('retryGeneration'\)/);
  assert.match(i18n, /重试生成/);
});

test('the chat page never shadows the Makers chat agent route', async () => {
  const [rawConfig, landingPage, chatPage] = await Promise.all([
    read('edgeone.json'),
    read('frontend/index.html'),
    read('frontend/chatBot/index.html'),
  ]);
  const config = JSON.parse(rawConfig);
  const frontendRewrites = config.rewrites || [];
  assert.equal(
    frontendRewrites.some((item) => item.source === '/chat'),
    false,
    'POST /chat belongs to the Makers Agent and must not be rewritten to static HTML',
  );
  assert.deepEqual(
    frontendRewrites.find((item) => item.source === '/chatBot'),
    { source: '/chatBot', destination: '/chatBot/index.html' },
  );
  assert.match(landingPage, /href="\/chatBot"/);
  assert.match(chatPage, /src="\/src\/main\.tsx"/);
});
