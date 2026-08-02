import { AUTH_TYPES } from './generated/entitlements.js';

const SESSION_COOKIE = 'floris_session';
const OAUTH_NONCE_COOKIE = 'floris_oauth_nonce';

export class AuthError extends Error {
  constructor(message = 'Unauthorized', code = 'UNAUTHORIZED') {
    super(message);
    this.name = 'AuthError';
    this.code = code;
  }
}

function base64UrlEncode(value) {
  const bytes = value instanceof Uint8Array
    ? value
    : new TextEncoder().encode(String(value));
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary)
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/g, '');
}

function base64UrlDecode(value) {
  const normalized = String(value || '')
    .replace(/-/g, '+')
    .replace(/_/g, '/');
  const padded = normalized + '='.repeat((4 - normalized.length % 4) % 4);
  const binary = atob(padded);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

function jsonFromBase64Url(value) {
  return JSON.parse(new TextDecoder().decode(base64UrlDecode(value)));
}

function runtimeEnv(requestOrContext, override) {
  if (override && typeof override === 'object') return override;
  if (requestOrContext?.env && typeof requestOrContext.env === 'object') {
    return requestOrContext.env;
  }
  return {};
}

function runtimeRequest(requestOrContext) {
  if (requestOrContext?.request) return requestOrContext.request;
  return requestOrContext;
}

function sessionSecret(env) {
  const secret = String(env.JWT_SECRET || '').trim();
  if (secret.length < 32) {
    throw new AuthError(
      'JWT_SECRET must contain at least 32 characters in public mode',
      'AUTH_NOT_CONFIGURED',
    );
  }
  return secret;
}

async function hmacKey(secret, usage) {
  return crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    usage,
  );
}

export function readCookie(headers, name) {
  const raw = typeof headers?.get === 'function'
    ? headers.get('cookie')
    : headers?.cookie || headers?.Cookie || '';
  for (const part of String(raw || '').split(';')) {
    const separator = part.indexOf('=');
    if (separator < 0) continue;
    if (part.slice(0, separator).trim() === name) {
      return decodeURIComponent(part.slice(separator + 1).trim());
    }
  }
  return '';
}

export async function signSessionToken(payload, env, ttlSeconds = 60 * 60 * 24 * 7) {
  const now = Math.floor(Date.now() / 1000);
  const header = base64UrlEncode(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const body = base64UrlEncode(JSON.stringify({
    ...payload,
    iat: now,
    exp: now + Math.max(60, Math.floor(Number(ttlSeconds) || 0)),
  }));
  const input = `${header}.${body}`;
  const key = await hmacKey(sessionSecret(env), ['sign']);
  const signature = await crypto.subtle.sign(
    'HMAC',
    key,
    new TextEncoder().encode(input),
  );
  return `${input}.${base64UrlEncode(new Uint8Array(signature))}`;
}

export async function verifySessionToken(token, env, options = {}) {
  const parts = String(token || '').split('.');
  if (parts.length !== 3) throw new AuthError('Malformed session', 'INVALID_SESSION');
  let header;
  let payload;
  try {
    header = jsonFromBase64Url(parts[0]);
    payload = jsonFromBase64Url(parts[1]);
  } catch {
    throw new AuthError('Malformed session', 'INVALID_SESSION');
  }
  if (header?.alg !== 'HS256' || header?.typ !== 'JWT') {
    throw new AuthError('Unsupported session algorithm', 'INVALID_SESSION');
  }
  const key = await hmacKey(sessionSecret(env), ['verify']);
  const valid = await crypto.subtle.verify(
    'HMAC',
    key,
    base64UrlDecode(parts[2]),
    new TextEncoder().encode(`${parts[0]}.${parts[1]}`),
  );
  if (!valid) throw new AuthError('Invalid session signature', 'INVALID_SESSION');
  const now = Math.floor(Date.now() / 1000);
  if (!Number.isFinite(payload.exp) || payload.exp <= now) {
    throw new AuthError('Session expired', 'SESSION_EXPIRED');
  }
  if (payload.nbf && Number(payload.nbf) > now) {
    throw new AuthError('Session is not active', 'INVALID_SESSION');
  }
  if (options.purpose && payload.purpose !== options.purpose) {
    throw new AuthError('Session purpose mismatch', 'INVALID_SESSION');
  }
  return payload;
}

function safeSegment(value, fallback) {
  const normalized = String(value || '')
    .trim()
    .replace(/[^0-9A-Za-z._-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 96);
  return normalized || fallback;
}

export function storageUserId(tenantId, subjectId) {
  return `${safeSegment(tenantId, 'default')}:${safeSegment(subjectId, 'anonymous')}`;
}

export async function conversationIndexUserId(userOrId) {
  const raw = typeof userOrId === 'object' ? userOrId?.id : userOrId;
  const value = String(raw || '').trim();
  if (!value) throw new AuthError('Identity is required');
  const digest = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(value),
  );
  const hex = Array.from(
    new Uint8Array(digest),
    (byte) => byte.toString(16).padStart(2, '0'),
  ).join('');
  return `uid_${hex.slice(0, 40)}`;
}

export async function scopedConversationId(user, conversationId) {
  const raw = String(conversationId || '').trim();
  if (!raw || raw.length > 180) {
    throw new AuthError('Invalid conversation id', 'INVALID_CONVERSATION');
  }
  const digest = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(`${String(user?.id || '')}:${raw}`),
  );
  const hex = Array.from(
    new Uint8Array(digest),
    (byte) => byte.toString(16).padStart(2, '0'),
  ).join('');
  return `yb7_${hex.slice(0, 32)}`;
}

export function publicIdentity(payload) {
  const tenantId = safeSegment(payload.tenant_id, 'default');
  const subjectId = safeSegment(payload.sub || payload.subject_id, 'anonymous');
  const authType = AUTH_TYPES.includes(payload.auth_type)
    ? payload.auth_type
    : 'guest';
  const membership = ['guest', 'free', 'plus', 'pro'].includes(payload.membership)
    ? payload.membership
    : (authType === 'guest' ? 'guest' : 'free');
  return {
    id: storageUserId(tenantId, subjectId),
    subject_id: subjectId,
    tenant_id: tenantId,
    username: String(payload.username || payload.display_name || authType).slice(0, 80),
    display_name: String(payload.display_name || payload.username || '').slice(0, 120),
    avatar_url: String(payload.avatar_url || '').slice(0, 1000),
    auth_type: authType,
    auth_providers: Array.isArray(payload.auth_providers)
      ? payload.auth_providers.map(String).filter(Boolean).slice(0, 8)
      : [],
    membership,
    roles: Array.isArray(payload.roles)
      ? payload.roles.map(String).filter(Boolean).slice(0, 8)
      : [authType === 'guest' ? 'guest' : 'user'],
    session_version: Math.max(1, Number(payload.session_version) || 1),
    system: false,
  };
}

export async function currentUser(requestOrContext, envOverride) {
  const env = runtimeEnv(requestOrContext, envOverride);
  const request = runtimeRequest(requestOrContext);
  const token = readCookie(request?.headers, SESSION_COOKIE);
  if (!token) throw new AuthError('Authentication session is required');
  return publicIdentity(await verifySessionToken(token, env));
}

export function tenantPrefix(user) {
  if (!user) throw new AuthError('Identity is required');
  return `tenants/${safeSegment(user.tenant_id, 'default')}/users/${safeSegment(user.subject_id, 'anonymous')}/`;
}

export function sessionCookie(token, options = {}) {
  const maxAge = Math.max(0, Math.floor(Number(options.maxAge) || 0));
  const secure = options.secure === false ? '' : '; Secure';
  return `${SESSION_COOKIE}=${encodeURIComponent(token)}; Path=/; HttpOnly; SameSite=Lax${secure}; Max-Age=${maxAge}`;
}

export function clearSessionCookie(options = {}) {
  return sessionCookie('', { ...options, maxAge: 0 });
}

export function oauthNonceCookie(nonce, options = {}) {
  const secure = options.secure === false ? '' : '; Secure';
  return `${OAUTH_NONCE_COOKIE}=${encodeURIComponent(String(nonce || ''))}; Path=/auth/wechat; HttpOnly; SameSite=Lax${secure}; Max-Age=600`;
}

export function readOAuthNonce(request) {
  return readCookie(request?.headers, OAUTH_NONCE_COOKIE);
}

export function clearOAuthNonceCookie(options = {}) {
  const secure = options.secure === false ? '' : '; Secure';
  return `${OAUTH_NONCE_COOKIE}=; Path=/auth/wechat; HttpOnly; SameSite=Lax${secure}; Max-Age=0`;
}

export const sessionConstants = Object.freeze({
  cookieName: SESSION_COOKIE,
  oauthNonceCookieName: OAUTH_NONCE_COOKIE,
});
