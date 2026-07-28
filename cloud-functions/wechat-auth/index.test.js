import test from 'node:test';
import assert from 'node:assert/strict';
import {
  assertConversationForUser,
  conversationPrefixForUser,
  currentUser,
  signMiniappSession,
  tenantPrefix,
  verifyMiniappSession,
} from '../../auth/current-user.js';
import { onRequest } from './index.js';

const secret = 'test-only-miniapp-session-secret';

test('web calls keep the existing local owner identity', async () => {
  const user = await currentUser(new Request('https://floris.test/system'), {});
  assert.equal(user.id, 'local-user');
  assert.equal(user.conversationPrefix, 'yb7_');
  assert.equal(tenantPrefix(user), '');
});

test('signed miniapp sessions isolate conversation and blob namespaces', async () => {
  const userId = 'wx_1234567890abcdef12345678';
  const token = signMiniappSession({ userId, expiresAt: Date.now() + 60_000 }, secret);
  const verified = verifyMiniappSession(token, secret);
  assert.equal(verified.id, userId);
  assert.equal(verified.conversationPrefix, conversationPrefixForUser(userId));
  assert.match(tenantPrefix(verified), /^users\/wx_/);
  const conversation = `${verified.conversationPrefix}abc123`;
  assert.equal(assertConversationForUser(conversation, verified), conversation);
  assert.throws(() => assertConversationForUser('yb7_someone_else_abc', verified));

  const request = new Request('https://floris.test/messages', {
    headers: { Authorization: `Bearer ${token}` },
  });
  assert.equal((await currentUser(request, { MINIAPP_SESSION_SECRET: secret })).id, userId);
  await assert.rejects(
    currentUser(request, { MINIAPP_SESSION_SECRET: 'wrong-secret' }),
    /Unauthorized/,
  );
});

test('expired and tampered miniapp sessions are rejected', () => {
  const token = signMiniappSession({
    userId: 'wx_1234567890abcdef12345678',
    expiresAt: Date.now() - 1_000,
  }, secret);
  assert.throws(() => verifyMiniappSession(token, secret), /Unauthorized/);
  assert.throws(() => verifyMiniappSession(`${token}x`, secret), /Unauthorized/);
});

test('wechat-auth exchanges wx.login code without exposing openid or session_key', async () => {
  const response = await onRequest({
    request: new Request('https://floris.test/wechat-auth', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ code: 'temporary-code' }),
    }),
    env: {
      WECHAT_MINIAPP_APP_ID: 'wx-app-id',
      WECHAT_MINIAPP_APP_SECRET: 'wx-app-secret',
      MINIAPP_SESSION_SECRET: secret,
    },
    fetch: async (url) => {
      assert.match(String(url), /jscode2session/);
      assert.match(String(url), /js_code=temporary-code/);
      return new Response(JSON.stringify({
        openid: 'openid-is-never-returned',
        session_key: 'session-key-is-never-returned',
      }), { status: 200 });
    },
  });
  assert.equal(response.status, 200);
  const body = await response.json();
  assert.match(body.token, /\./);
  assert.match(body.user_id, /^wx_/);
  assert.match(body.conversation_prefix, /^yb7_/);
  assert.equal(body.openid, undefined);
  assert.equal(body.session_key, undefined);
  assert.equal(verifyMiniappSession(body.token, secret).id, body.user_id);
});
