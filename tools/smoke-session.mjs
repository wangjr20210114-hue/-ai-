const SESSION_COOKIE_NAME = 'floris_session';


function normalizedBaseUrl(value) {
  const baseUrl = String(value || '').trim().replace(/\/+$/, '');
  if (!/^https?:\/\//i.test(baseUrl)) {
    throw new Error('FLORIS_SMOKE_BASE_URL must be an absolute HTTP(S) URL');
  }
  return baseUrl;
}


function normalizedAuthQuery(value) {
  return String(value || '').trim().replace(/^\?/, '');
}


function endpointFor(baseUrl, authQuery, path) {
  const url = new URL(path, `${baseUrl}/`);
  const source = new URLSearchParams(authQuery);
  for (const [key, value] of source) {
    if (!url.searchParams.has(key)) url.searchParams.set(key, value);
  }
  return url.toString();
}


function sessionCookie(value) {
  const raw = String(value || '').trim();
  const match = new RegExp(`(?:^|[;,]\\s*)(${SESSION_COOKIE_NAME}=[^;,\\s]+)`).exec(raw);
  return match?.[1] || '';
}


function requireLoginEnabled(value) {
  return /^(?:1|true|yes)$/i.test(String(value || '').trim());
}


function idSegment(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^0-9a-z._-]+/g, '-')
    .replace(/^-+|-+$/g, '');
}


/** Return a Maker-compatible, collision-resistant conversation identifier. */
export function createSmokeConversationId(label = 'smoke', discriminator = '') {
  const stamp = Date.now().toString(36);
  const tail = idSegment(discriminator).slice(0, 6);
  const fixedLength = `smk--${stamp}${tail ? `-${tail}` : ''}`.length;
  const prefix = (idSegment(label) || 'smoke').slice(0, Math.max(1, 36 - fixedLength));
  const id = `smk-${prefix}-${stamp}${tail ? `-${tail}` : ''}`;
  if (id.length < 6 || id.length > 36 || !/^[0-9a-zA-Z-_.]+$/.test(id)) {
    throw new Error('Could not create a Maker-compatible smoke conversation id');
  }
  return id;
}


async function readSession(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data?.identity || !data?.entitlements || !data?.login) {
    throw new Error(
      `Smoke authentication failed: HTTP ${response.status} ${String(data?.error || '').slice(0, 180)}`,
    );
  }
  return data;
}


/**
 * Authenticate production/dev smoke requests through the same public contract
 * as real clients. Web smoke runs use the signed HttpOnly-style Cookie minted
 * by /auth/session; native/mobile smoke runs use a short-lived Bearer supplied
 * only through the process environment.
 */
export async function createSmokeClient({
  baseUrl,
  authQuery = '',
  fetchImpl = globalThis.fetch,
  env = process.env,
} = {}) {
  if (typeof fetchImpl !== 'function') throw new Error('A fetch implementation is required');
  const root = normalizedBaseUrl(baseUrl || env.FLORIS_SMOKE_BASE_URL);
  const previewQuery = normalizedAuthQuery(authQuery || env.FLORIS_SMOKE_AUTH_QUERY);
  const bearerToken = String(env.FLORIS_SMOKE_BEARER_TOKEN || '').trim();
  let cookie = sessionCookie(env.FLORIS_SMOKE_SESSION_COOKIE);

  const endpoint = (path) => endpointFor(root, previewQuery, path);
  const authHeaders = () => {
    if (bearerToken) return { Authorization: `Bearer ${bearerToken}` };
    if (cookie) return { Cookie: cookie };
    return {};
  };
  const request = (path, init = {}) => {
    const headers = new Headers(init.headers || {});
    for (const [name, value] of Object.entries(authHeaders())) headers.set(name, value);
    return fetchImpl(endpoint(path), { ...init, headers });
  };

  const sessionResponse = await request('/auth/session', {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });
  const renewedCookie = sessionCookie(sessionResponse.headers.get('set-cookie'));
  if (renewedCookie && !bearerToken) cookie = renewedCookie;
  const session = await readSession(sessionResponse);
  const requireLogin = requireLoginEnabled(env.FLORIS_SMOKE_REQUIRE_LOGIN);
  if (requireLogin && session.identity.auth_type === 'guest') {
    throw new Error(
      'Authenticated smoke was required, but /auth/session returned a guest identity',
    );
  }
  if (!bearerToken && !cookie) {
    throw new Error('/auth/session did not mint or renew the signed Web session cookie');
  }

  return Object.freeze({
    baseUrl: root,
    endpoint,
    fetch: request,
    session,
    auth: Object.freeze({
      transport: bearerToken ? 'bearer' : 'cookie',
      auth_type: session.identity.auth_type,
      membership: session.identity.membership,
      require_login: requireLogin,
    }),
  });
}
