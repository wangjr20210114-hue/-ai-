import test from 'node:test';
import assert from 'node:assert/strict';

import {
  currentUser,
  conversationIndexUserId,
  readSessionToken,
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

test('native Bearer sessions resolve through the same tenant identity contract', async () => {
  const token = await signSessionToken(testIdentity({
    auth_type: 'cloudbase',
    membership: 'plus',
  }), TEST_AUTH_ENV, 600);
  const request = new Request('https://example.test/system', {
    headers: { Authorization: `Bearer ${token}` },
  });
  const user = await currentUser(request, TEST_AUTH_ENV);
  assert.equal(user.id, 'floris:11111111-1111-4111-8111-111111111111');
  assert.equal(user.auth_type, 'cloudbase');
  assert.equal(user.membership, 'plus');
});

test('an explicit native Bearer wins over an unrelated WebView cookie', async () => {
  const cookieToken = await signSessionToken(testIdentity({
    sub: '22222222-2222-4222-8222-222222222222',
    auth_type: 'guest',
    membership: 'guest',
  }), TEST_AUTH_ENV, 600);
  const bearerToken = await signSessionToken(testIdentity({
    auth_type: 'cloudbase',
  }), TEST_AUTH_ENV, 600);
  const headers = new Headers({
    Cookie: `floris_session=${cookieToken}`,
    Authorization: `Bearer ${bearerToken}`,
  });
  assert.equal(readSessionToken(headers), bearerToken);
  const user = await currentUser(new Request('https://example.test/system', { headers }), TEST_AUTH_ENV);
  assert.equal(user.auth_type, 'cloudbase');
  assert.equal(user.subject_id, '11111111-1111-4111-8111-111111111111');
});

test('conversation user indexes are deterministic and path-safe across runtimes', async () => {
  const first = 'floris:11111111-1111-4111-8111-111111111111';
  const second = 'floris:22222222-2222-4222-8222-222222222222';
  const firstIndex = await conversationIndexUserId(first);
  assert.match(firstIndex, /^uid_[0-9a-f]{40}$/);
  assert.equal(firstIndex, 'uid_e236542cf226407ddc32fea8e80052d0bfde5881');
  assert.equal(firstIndex, await conversationIndexUserId({ id: first }));
  assert.notEqual(firstIndex, await conversationIndexUserId(second));
  await assert.rejects(conversationIndexUserId(null), /identity/i);
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
