import { createHmac, timingSafeEqual } from 'node:crypto';

const TOKEN_VERSION = 1;
const LEGACY_USER = Object.freeze({
  id: 'local-user',
  username: 'local-user',
  roles: ['owner'],
  conversationPrefix: 'yb7_',
});

function base64UrlEncode(value) {
  return Buffer.from(value).toString('base64url');
}

function base64UrlDecode(value) {
  return Buffer.from(String(value || ''), 'base64url').toString('utf8');
}

function signature(payload, secret) {
  return createHmac('sha256', secret).update(payload).digest('base64url');
}

function bearerToken(request) {
  const value = request?.headers?.get?.('authorization')
    || request?.headers?.get?.('Authorization')
    || '';
  return String(value).match(/^Bearer\s+(.+)$/i)?.[1]?.trim() || '';
}

export function conversationPrefixForUser(userId) {
  if (userId === LEGACY_USER.id) return LEGACY_USER.conversationPrefix;
  const tag = String(userId || '').replace(/[^0-9A-Za-z]/g, '').slice(-10);
  if (!tag) throw new Error('Invalid user id');
  return `yb7_${tag}_`;
}

export function signMiniappSession(
  { userId, username = '微信用户', expiresAt },
  secret,
) {
  if (!secret || !String(userId || '').startsWith('wx_')) {
    throw new Error('Miniapp session is not configured');
  }
  const payload = base64UrlEncode(JSON.stringify({
    v: TOKEN_VERSION,
    sub: userId,
    name: username,
    exp: Math.floor(Number(expiresAt) / 1000),
    conversation_prefix: conversationPrefixForUser(userId),
  }));
  return `${payload}.${signature(payload, secret)}`;
}

export function verifyMiniappSession(token, secret, now = Date.now()) {
  const [payload, providedSignature, extra] = String(token || '').split('.');
  if (!payload || !providedSignature || extra || !secret) throw new Error('Unauthorized');
  const expectedSignature = signature(payload, secret);
  const provided = Buffer.from(providedSignature);
  const expected = Buffer.from(expectedSignature);
  if (provided.length !== expected.length || !timingSafeEqual(provided, expected)) {
    throw new Error('Unauthorized');
  }
  let claims;
  try {
    claims = JSON.parse(base64UrlDecode(payload));
  } catch {
    throw new Error('Unauthorized');
  }
  if (
    claims?.v !== TOKEN_VERSION
    || !String(claims?.sub || '').startsWith('wx_')
    || Number(claims?.exp || 0) <= Math.floor(now / 1000)
    || claims?.conversation_prefix !== conversationPrefixForUser(claims.sub)
  ) {
    throw new Error('Unauthorized');
  }
  return {
    id: String(claims.sub),
    username: String(claims.name || '微信用户'),
    roles: ['member'],
    conversationPrefix: String(claims.conversation_prefix),
  };
}

/**
 * Keep the existing personal web deployment backward compatible while
 * authenticating mini-program calls with a server-signed wx.login session.
 */
export async function currentUser(request, env = {}) {
  const token = bearerToken(request);
  if (!token) return { ...LEGACY_USER };
  return verifyMiniappSession(token, env.MINIAPP_SESSION_SECRET);
}

export function assertConversationForUser(value, user) {
  const raw = String(value || '').trim();
  const prefix = String(user?.conversationPrefix || conversationPrefixForUser(user?.id));
  if (
    !raw
    || raw.length > 36
    || !/^[0-9A-Za-z._-]+$/.test(raw)
    || !raw.startsWith(prefix)
  ) {
    throw new Error('Invalid conversation id');
  }
  return raw;
}

export function tenantPrefix(user) {
  return user?.id === LEGACY_USER.id ? '' : `users/${user.id}/`;
}
