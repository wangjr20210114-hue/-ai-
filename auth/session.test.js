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
import {
  normalizeMembership,
  publicEntitlements,
  skillAccess,
} from './entitlements.js';

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
  const [header, payload, signature] = token.split('.');
  const tamperedSignature = `${signature.startsWith('a') ? 'b' : 'a'}${signature.slice(1)}`;
  await assert.rejects(
    verifySessionToken(`${header}.${payload}.${tamperedSignature}`, TEST_AUTH_ENV),
    /signature/i,
  );
  await assert.rejects(
    verifySessionToken(token, TEST_AUTH_ENV, { purpose: 'oauth' }),
    /purpose/i,
  );
});

test('entitlements consume the generated contract for every plan', () => {
  assert.equal(normalizeMembership('unknown', 'guest'), 'guest');
  assert.equal(normalizeMembership('unknown', 'wechat'), 'free');
  assert.deepEqual(publicEntitlements({ auth_type: 'guest', membership: 'guest' }), {
    plan: 'guest',
    limits: {
      searchDepth: 'basic',
      concurrentRuns: 1,
      dailyTokens: 20_000,
      userSkillUploads: 0,
    },
    payment_available: false,
  });
  assert.deepEqual(skillAccess({ auth_type: 'guest' }, 'core'), {
    allowed: true,
    reason: 'login_required',
  });
  assert.deepEqual(skillAccess({ auth_type: 'guest' }, 'web-search'), {
    allowed: false,
    reason: 'login_required',
  });
});
