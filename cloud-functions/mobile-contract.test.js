import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const ROOT = new URL('../', import.meta.url);

async function json(path) {
  return JSON.parse(await readFile(new URL(path, ROOT), 'utf8'));
}

test('v1 publishes one cross-platform API and forward-compatible event contract', async () => {
  const [api, events, components] = await Promise.all([
    json('frontend/public/contracts/floris-client-v1.openapi.json'),
    json('frontend/public/contracts/chat-events-v1.schema.json'),
    json('frontend/public/contracts/floris-components-v1.schema.json'),
  ]);
  assert.equal(api.openapi, '3.1.0');
  assert.ok(api.paths['/auth/mobile/session']);
  assert.ok(api.paths['/chat'].post.responses['200']['x-floris-event-schema']);
  assert.equal(api.components.securitySchemes.florisBearer.scheme, 'bearer');
  assert.equal(api.components.securitySchemes.browserSession.in, 'cookie');
  assert.equal(api['x-floris-compatibility'].unknown_sse_events, 'ignore');
  assert.equal(api['x-floris-compatibility'].component_schema, '/contracts/floris-components-v1.schema.json');
  assert.ok(Array.isArray(events.anyOf));
  assert.equal(events.oneOf, undefined);
  const eventSchema = JSON.stringify(events);
  for (const type of [
    'ai_response', 'ai_response_reset', 'tool_call', 'tool_result',
    'progress_event', 'search_results', 'search_media', 'paper_results',
    'calendar_action', 'map_action', 'side_effect_action',
    'clarification_action', 'browser_location_request', 'experience_hint',
    'answer_complete', 'follow_ups', 'proactive_update', 'usage', 'ping',
    'error_message',
  ]) {
    assert.match(eventSchema, new RegExp(type));
  }
  assert.deepEqual(
    components.$defs.workspaceAction.properties.kind.enum,
    ['map_recommendation', 'calendar_changes', 'meeting_create', 'image_generate'],
  );
  assert.ok(components.$defs.media.properties.source_id);
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
