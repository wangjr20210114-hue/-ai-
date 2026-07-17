// Adapted from TencentEdgeOne/makers-agents-auth. Web Crypto keeps signing and
// verification compatible with Edge Middleware and EdgeOne Functions.
export const COOKIE_NAME = 'jwt_token';
export const DEFAULT_TTL_SECONDS = 7 * 24 * 60 * 60;

const encoder = new TextEncoder();
const encodeBase64Url = (value) => {
  const bytes = typeof value === 'string' ? encoder.encode(value) : value;
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
};
const decodeBase64Url = (value) => {
  const text = String(value);
  const binary = atob(text.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - text.length % 4) % 4));
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
};

async function importKey(secret, usage) {
  if (!secret || String(secret).length < 32) throw new Error('JWT_SECRET must contain at least 32 characters');
  return crypto.subtle.importKey('raw', encoder.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, [usage]);
}

export function readCookie(headers, key = COOKIE_NAME) {
  const raw = headers?.get?.('cookie') || headers?.cookie || headers?.Cookie || '';
  for (const part of raw.split(';')) {
    const index = part.indexOf('=');
    if (index >= 0 && part.slice(0, index).trim() === key) return decodeURIComponent(part.slice(index + 1).trim());
  }
  return '';
}

export async function signToken(payload, env, ttlSeconds = DEFAULT_TTL_SECONDS) {
  const now = Math.floor(Date.now() / 1000);
  const header = encodeBase64Url(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const body = encodeBase64Url(JSON.stringify({ ...payload, iat: now, exp: now + ttlSeconds }));
  const key = await importKey(env?.JWT_SECRET, 'sign');
  const signature = await crypto.subtle.sign('HMAC', key, encoder.encode(`${header}.${body}`));
  return `${header}.${body}.${encodeBase64Url(new Uint8Array(signature))}`;
}

export async function verifyToken(token, env) {
  const parts = String(token || '').split('.');
  if (parts.length !== 3) throw new Error('invalid session');
  const header = JSON.parse(new TextDecoder().decode(decodeBase64Url(parts[0])));
  if (header.alg !== 'HS256') throw new Error('unsupported session algorithm');
  const key = await importKey(env?.JWT_SECRET, 'verify');
  const valid = await crypto.subtle.verify('HMAC', key, decodeBase64Url(parts[2]), encoder.encode(`${parts[0]}.${parts[1]}`));
  if (!valid) throw new Error('invalid session signature');
  const payload = JSON.parse(new TextDecoder().decode(decodeBase64Url(parts[1])));
  if (!payload.sub || Number(payload.exp || 0) < Math.floor(Date.now() / 1000)) throw new Error('expired session');
  return payload;
}

export async function requireAuth({ request, env }) {
  return verifyToken(readCookie(request.headers), env);
}

export function serializeSession(token, maxAge = DEFAULT_TTL_SECONDS) {
  return `${COOKIE_NAME}=${token}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${maxAge}`;
}

export function clearSession() {
  return `${COOKIE_NAME}=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0`;
}
