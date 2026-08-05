import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';

const ROOT = new URL('../', import.meta.url);

async function json(path) {
  return JSON.parse(await readFile(new URL(path, ROOT), 'utf8'));
}

async function text(path) {
  return readFile(new URL(path, ROOT), 'utf8');
}

function ownedRoutes(source) {
  const declaration = source.match(/export const routes = Object\.freeze\(\[([\s\S]*?)\]\)/);
  if (!declaration) return [];
  return [...declaration[1].matchAll(/['"](\/[^'"]+)['"]/g)].map((match) => match[1]);
}

async function sourceFiles(directory) {
  const files = [];
  for (const entry of await readdir(new URL(directory, ROOT), { withFileTypes: true })) {
    const path = `${directory}${entry.name}`;
    if (entry.isDirectory()) files.push(...await sourceFiles(`${path}/`));
    else if (/\.(?:ts|tsx)$/.test(entry.name) && !/\.test\./.test(entry.name)) {
      files.push(path);
    }
  }
  return files;
}

function literalClientRoutes(source) {
  const routes = [];
  const calls = source.matchAll(
    /\b(?:authorizedFetch|requestJson|streamEvents|withEdgeOneAuth)(?:<[^;{}()]*>)?\s*\(\s*(['"`])(\/[A-Za-z0-9_/-]+)/g,
  );
  for (const call of calls) routes.push(call[2]);
  return routes;
}

function pointerValue(document, pointer) {
  return pointer
    .replace(/^#\//, '')
    .split('/')
    .map((part) => part.replaceAll('~1', '/').replaceAll('~0', '~'))
    .reduce((value, part) => value?.[part], document);
}

function refs(value, output = []) {
  if (!value || typeof value !== 'object') return output;
  if (typeof value.$ref === 'string') output.push(value.$ref);
  for (const item of Object.values(value)) refs(item, output);
  return output;
}

test('v1 publishes one cross-platform API and forward-compatible event contract', async () => {
  const [api, events, components, guide] = await Promise.all([
    json('frontend/public/contracts/floris-client-v1.openapi.json'),
    json('frontend/public/contracts/chat-events-v1.schema.json'),
    json('frontend/public/contracts/floris-components-v1.schema.json'),
    text('frontend/public/contracts/mobile-client-v1.md'),
  ]);
  assert.equal(api.openapi, '3.1.0');
  assert.equal(api.info.version, '1.4.0');
  assert.ok(api.paths['/auth/mobile/session']);
  assert.ok(api.paths['/chat'].post.responses['200']['x-floris-event-schema']);
  assert.ok(api.paths['/reader'].post.responses['200']['x-floris-event-schema']);
  assert.ok(api.paths['/image'].post.responses['200']['x-floris-event-schema']);
  assert.equal(api.components.securitySchemes.florisBearer.scheme, 'bearer');
  assert.equal(api.components.securitySchemes.browserSession.in, 'cookie');
  assert.equal(api['x-floris-compatibility'].unknown_sse_events, 'ignore');
  assert.equal(api['x-floris-compatibility'].component_schema, '/contracts/floris-components-v1.schema.json');
  assert.equal(api['x-floris-compatibility'].source_media_binding, 'source_id');
  assert.equal(
    api['x-floris-compatibility'].search_media_policy,
    'vision_reviewed_and_exact_inline_source_or_omit',
  );
  assert.equal(api['x-floris-compatibility'].json_wire_naming, 'snake_case');
  assert.deepEqual(
    Object.keys(api['x-floris-client-surfaces']).sort(),
    ['chat', 'files', 'maintenance', 'maps', 'papers', 'personalization', 'profile', 'session', 'skills', 'workspace'],
  );
  assert.deepEqual(
    Object.keys(api['x-floris-platform-adapters']).sort(),
    ['identity_provider', 'local_files', 'map_renderer', 'presigned_upload', 'system_location'],
  );
  assert.equal(
    api.paths['/skill-uploads'].post.requestBody.content['application/json'].schema.$ref,
    '#/components/schemas/SkillUploadMutationRequest',
  );
  assert.ok(Array.isArray(events.anyOf));
  assert.equal(events.oneOf, undefined);
  assert.equal(events.$defs.openEvent, undefined, 'the v1 schema must reject unknown event types');
  assert.ok(events.anyOf.every((branch) => branch.$ref !== '#/$defs/base'));
  const eventSchema = JSON.stringify(events);
  for (const type of [
    'ai_response', 'ai_response_reset', 'tool_call', 'tool_result',
    'progress_event', 'search_results', 'search_media', 'paper_results',
    'calendar_action', 'map_action', 'side_effect_action',
    'clarification_action', 'browser_location_request', 'experience_hint',
    'answer_complete', 'follow_ups', 'proactive_update', 'usage', 'ping',
    'paper_source', 'paper_delta', 'paper_done', 'image_progress', 'image_action',
    'error_message',
  ]) {
    assert.match(eventSchema, new RegExp(type));
  }
  assert.deepEqual(
    components.$defs.workspaceAction.properties.kind.enum,
    ['map_recommendation', 'calendar_changes', 'meeting_create', 'image_generate'],
  );
  assert.ok(components.$defs.media.properties.source_id);
  assert.equal(
    components.$defs.reviewedSearchMedia.allOf[1].properties.vision_reviewed.const,
    true,
  );
  assert.equal(
    components.$defs.searchMeta.properties.media.items.$ref,
    '#/$defs/reviewedSearchMedia',
  );
  assert.equal(api.components.schemas.SearchPreferences.additionalProperties, false);
  assert.equal(
    api.components.schemas.MapPreferences.required.length,
    8,
  );
  assert.ok(api.components.schemas.ProactiveNotification.properties.action_prompt);
  assert.ok(api.components.schemas.ProactiveNotification.properties.snoozed_until);
  assert.equal(api.components.schemas.ProactiveNotification.properties.actionPrompt, undefined);
  assert.equal(api.components.schemas.ProactiveNotification.properties.snoozedUntil, undefined);
  assert.ok(api.paths['/document-text']);
  assert.ok(api.components.schemas.ReaderRequest.anyOf);
  assert.ok(api.components.schemas.ReaderRequest.properties.file_id);
  assert.ok(api.components.schemas.SkillPreferenceResult);
  assert.ok(api.components.schemas.SavedPaper.required.includes('storage_key'));
  assert.equal(
    api.paths['/intelligence'].post.requestBody.content['application/json'].schema.$ref,
    '#/components/schemas/IntelligenceOperationRequest',
  );
  assert.equal(
    api.paths['/proactive'].post.requestBody.content['application/json'].schema.$ref,
    '#/components/schemas/ProactiveOperationRequest',
  );
  assert.ok(components.$defs.routePlan.properties.legs);
  assert.ok(components.$defs.routeLeg.properties.sections);
  assert.ok(components.$defs.componentPublicationBatch);
  assert.deepEqual(
    components.$defs.componentPublication.required,
    ['version', 'action', 'payload'],
  );
  const publicComponentEnvelope = JSON.stringify(components.$defs.componentPublicationBatch);
  assert.doesNotMatch(publicComponentEnvelope, /tenant_id|user_id|request_id/);
  assert.match(guide, /Android.*HarmonyOS.*iOS/s);
  assert.match(guide, /source_id/);
  assert.match(guide, /search_media.*可以与.*ai_response.*交错到达/s);
  assert.match(guide, /未完成、失败或未通过的候选一律不显示/);
  assert.match(guide, /action_prompt.*snoozed_until/s);
  assert.doesNotMatch(guide, /GitHub\s*(?:登录|登入|OAuth|login)/i);
  for (const path of Object.keys(api.paths)) {
    assert.match(guide, new RegExp(path.replaceAll('/', '\\/')));
  }
  for (const reference of refs(api)) {
    if (reference.startsWith('#/')) {
      assert.ok(pointerValue(api, reference), `unresolved OpenAPI ref ${reference}`);
      continue;
    }
    const [file, pointer] = reference.replace(/^\.\//, '').split('#');
    assert.equal(file, 'floris-components-v1.schema.json');
    assert.ok(pointerValue(components, `#${pointer}`), `unresolved component ref ${reference}`);
  }
  for (const reference of refs(events)) {
    if (reference.startsWith('#/')) {
      assert.ok(pointerValue(events, reference), `unresolved event ref ${reference}`);
      continue;
    }
    const [file, pointer] = reference.split('#');
    assert.equal(file, 'floris-components-v1.schema.json');
    assert.ok(pointerValue(components, `#${pointer}`), `unresolved event component ref ${reference}`);
  }
});

test('personalization wire fields and answer quality stay backend-authoritative', async () => {
  const [
    settingsView,
    intelligenceController,
    turnService,
    richSearch,
    mediaPresenter,
    documentText,
    readerController,
    files,
  ] = await Promise.all([
    text('frontend/src/features/settings/view/AppSettingsButton.tsx'),
    text('agents/_controllers/intelligence_controller.py'),
    text('agents/_application/chat/turn_service.py'),
    text('agents/_infrastructure/providers/rich_search.py'),
    text('frontend/src/features/search/model/sourceBoundMedia.ts'),
    text('cloud-functions/document-text/index.js'),
    text('agents/_controllers/reader_controller.py'),
    text('cloud-functions/files/index.js'),
  ]);
  assert.match(settingsView, /intelligence\('update_search_preferences'/);
  assert.match(settingsView, /intelligence\('update_map_preferences'/);
  assert.match(intelligenceController, /operation == "update_search_preferences"/);
  assert.match(turnService, /search_preferences\.get\("result_limit"\)/);
  assert.match(turnService, /search_preferences\.get\("image_limit"\)/);
  assert.match(turnService, /public_answer_model=model/);
  assert.doesNotMatch(richSearch, /_source_bound_fallback_candidates/);
  assert.doesNotMatch(mediaPresenter, /placeUncited/);
  assert.match(mediaPresenter, /item\.vision_reviewed === true/);
  assert.match(documentText, /@edgeone\/pages-blob/);
  assert.match(documentText, /pdfjs-dist\/legacy\/build\/pdf\.mjs/);
  assert.match(readerController, /body\.get\("file_id"\)/);
  assert.doesNotMatch(files, /Accept-Ranges/);
  assert.match(files, /X-Floris-Part-Protocol/);
});

test('every client-owned display route is published in the v1 OpenAPI', async () => {
  const [api, ...clients] = await Promise.all([
    json('frontend/public/contracts/floris-client-v1.openapi.json'),
    text('frontend/src/features/calendar/model/client.ts'),
    text('frontend/src/features/chat/model/client.ts'),
    text('frontend/src/features/image-studio/model/client.ts'),
    text('frontend/src/features/maps/model/client.ts'),
    text('frontend/src/features/papers/model/client.ts'),
    text('frontend/src/features/settings/model/client.ts'),
    text('frontend/src/features/skills/model/client.ts'),
  ]);
  const featureRoutes = clients.flatMap(ownedRoutes);
  assert.ok(featureRoutes.length > 0);
  assert.deepEqual(
    featureRoutes.filter((route, index) => featureRoutes.indexOf(route) !== index),
    [],
    'one endpoint must have exactly one feature model owner',
  );
  for (const route of featureRoutes) {
    assert.ok(api.paths[route], `${route} is client-owned but missing from OpenAPI`);
  }
  for (const route of [
    '/auth/cloudbase/session',
    '/auth/logout',
    '/auth/mobile/session',
    '/profile',
  ]) {
    assert.ok(api.paths[route], `${route} is a public client boundary`);
  }
  assert.equal(api.paths['/skills'], undefined, 'internal Skills packages are not a public route');
  const operationIds = [];
  for (const [path, operations] of Object.entries(api.paths)) {
    for (const [method, operation] of Object.entries(operations)) {
      if (!['get', 'head', 'post', 'put', 'patch', 'delete'].includes(method)) continue;
      assert.ok(operation.operationId, `${method.toUpperCase()} ${path} needs an operationId`);
      operationIds.push(operation.operationId);
      assert.ok(operation.responses?.['200'], `${method.toUpperCase()} ${path} needs a 200 contract`);
    }
  }
  assert.equal(operationIds.length, new Set(operationIds).size, 'operationId values must be unique');
});

test('every literal frontend backend call is covered by the public client contract', async () => {
  const [api, files] = await Promise.all([
    json('frontend/public/contracts/floris-client-v1.openapi.json'),
    sourceFiles('frontend/src/'),
  ]);
  const calls = [];
  for (const file of files) {
    const source = await text(file);
    for (const route of literalClientRoutes(source)) calls.push({ file, route });
  }
  assert.ok(calls.length > 0);
  for (const { file, route } of calls) {
    assert.ok(api.paths[route], `${file} calls ${route}, which is missing from OpenAPI`);
  }
});

test('feature and component code cannot bypass the shared client transport', async () => {
  const files = [
    ...await sourceFiles('frontend/src/features/'),
    ...await sourceFiles('frontend/src/components/'),
  ];
  for (const file of files) {
    const source = await text(file);
    assert.doesNotMatch(
      source,
      /\b(?:fetch|XMLHttpRequest|WebSocket|EventSource)\s*\(/,
      `${file} must call its feature model and the shared transport`,
    );
  }
});

test('off-origin writes are limited to server-issued upload URLs', async () => {
  const files = await sourceFiles('frontend/src/');
  const directRawWrites = [];
  for (const file of files) {
    const source = await text(file);
    if (/requestRaw\([\s\S]{0,600}?\},\s*false\s*\)/.test(source)) {
      directRawWrites.push(file);
    }
  }
  assert.deepEqual(directRawWrites.sort(), [
    'frontend/src/features/auth/model/profileClient.ts',
    'frontend/src/features/chat/model/client.ts',
    'frontend/src/features/skills/model/client.ts',
  ]);
  const skillImport = await text('frontend/src/features/skills/model/userSkillImport.ts');
  const skillClient = await text('frontend/src/features/skills/model/client.ts');
  const skillBackend = await text('cloud-functions/skill-uploads/index.js');
  assert.doesNotMatch(skillImport, /shared\/transport|raw\.githubusercontent|gitlab\.com/);
  assert.match(skillClient, /operation:\s*'resolve_url'/);
  assert.match(skillBackend, /operation === 'resolve_url'/);
});

test('Node and Python authoritative identity adapters both accept Bearer transport', async () => {
  const [nodeIdentity, pythonIdentity, mobileController] = await Promise.all([
    readFile(new URL('auth/session.js', ROOT), 'utf8'),
    readFile(new URL('agents/_infrastructure/makers/identity.py', ROOT), 'utf8'),
    readFile(new URL('auth/controllers/cloudbase-controller.js', ROOT), 'utf8'),
  ]);
  assert.match(nodeIdentity, /readBearerToken/);
  assert.match(nodeIdentity, /readSessionToken/);
  assert.match(pythonIdentity, /scheme\.lower\(\) == "bearer"/);
  assert.match(mobileController, /exchangeCloudBaseIdentity\(context\)/);
  assert.doesNotMatch(mobileController, /refresh_token/);
});
