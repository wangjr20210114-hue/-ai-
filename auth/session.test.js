import test from 'node:test';
import assert from 'node:assert/strict';

import {
  currentUser,
  scopedConversationId,
  signSessionToken,
  storageUserId,
  tenantPrefix,
  verifySessionToken,
} from './session.js';
import {
  TEST_AUTH_ENV,
  authenticatedRequest,
  testIdentity,
} from '../test-utils/auth.js';

test('signed sessions resolve one tenant-scoped user', async () => {
  const request = await authenticatedRequest('https://example.test/system');
  const user = await currentUser(request, TEST_AUTH_ENV);
  assert.equal(user.id, 'floris:11111111-1111-4111-8111-111111111111');
  assert.equal(user.auth_type, 'wechat');
  assert.equal(tenantPrefix(user), 'tenants/floris/users/11111111-1111-4111-8111-111111111111/');
  assert.equal(storageUserId(user.tenant_id, user.subject_id), user.id);
});

test('conversation ids are deterministic and different across users', async () => {
  const first = {
    id: 'floris:11111111-1111-4111-8111-111111111111',
  };
  const second = {
    id: 'floris:22222222-2222-4222-8222-222222222222',
  };
  const firstId = await scopedConversationId(first, 'public-thread');
  assert.match(firstId, /^yb7_[0-9a-f]{32}$/);
  assert.equal(firstId, await scopedConversationId(first, 'public-thread'));
  assert.notEqual(firstId, await scopedConversationId(second, 'public-thread'));
});

test('tampered and wrong-purpose sessions are rejected', async () => {
  const token = await signSessionToken(testIdentity(), TEST_AUTH_ENV, 600);
  await assert.rejects(
    verifySessionToken(`${token.slice(0, -1)}${token.endsWith('a') ? 'b' : 'a'}`, TEST_AUTH_ENV),
    /signature/i,
  );
  await assert.rejects(
    verifySessionToken(token, TEST_AUTH_ENV, { purpose: 'oauth' }),
    /purpose/i,
  );
});
