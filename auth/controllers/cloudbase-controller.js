import { cloudBaseConfig } from '../cloudbase-config.js';
import {
  AuthError,
  currentUser,
  publicIdentity,
  sessionCookie,
  signSessionToken,
} from '../session.js';
import { jsonView } from '../views/http.js';

const USER_SESSION_TTL_SECONDS = 12 * 60 * 60;
const MAX_ACCESS_TOKEN_LENGTH = 16_384;

function sameOriginRequest(request) {
  const fetchSite = String(request.headers.get('sec-fetch-site') || '').toLowerCase();
  if (fetchSite) return fetchSite === 'same-origin';

  const origin = request.headers.get('origin');
  if (!origin) return true;
  const requestUrl = new URL(request.url);
  if (origin === requestUrl.origin) return true;

  const forwardedHost = String(
    request.headers.get('x-forwarded-host') || request.headers.get('host') || '',
  ).split(',', 1)[0].trim();
  const forwardedProto = String(
    request.headers.get('x-forwarded-proto') || requestUrl.protocol,
  ).split(',', 1)[0].trim().replace(/:$/, '');
  return Boolean(forwardedHost && origin === `${forwardedProto}://${forwardedHost}`);
}

function accessTokenFrom(body) {
  const value = String(body?.access_token || '').trim();
  if (!value || value.length > MAX_ACCESS_TOKEN_LENGTH || /\s/.test(value)) {
    throw new AuthError('A valid CloudBase access token is required', 'INVALID_CLOUDBASE_TOKEN');
  }
  return value;
}

async function cloudBaseProfile(config, accessToken) {
  const response = await fetch(`${config.gatewayOrigin}/auth/v1/user/me`, {
    method: 'GET',
    redirect: 'error',
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${accessToken}`,
      'X-Floris-Auth-Bridge': '1',
    },
  });
  const payload = await response.json().catch(() => ({}));
  const profile = payload?.data?.user || payload?.data || payload?.user || payload;
  const status = String(profile?.status || '').toUpperCase();
  if (!response.ok || !profile?.sub || (status && status !== 'ACTIVE')) {
    throw new AuthError('CloudBase rejected the user session', 'INVALID_CLOUDBASE_TOKEN');
  }
  return profile;
}

function providerNames(profile) {
  const values = [
    ...(Array.isArray(profile?.providers) ? profile.providers : []),
    ...(Array.isArray(profile?.app_metadata?.providers)
      ? profile.app_metadata.providers
      : []),
  ];
  return [...new Set(values
    .map((provider) => String(
      typeof provider === 'string'
        ? provider
        : provider?.id || provider?.provider || '',
    ).toLowerCase())
    .filter(Boolean))]
    .slice(0, 8);
}

function profileText(profile, ...keys) {
  for (const key of keys) {
    const value = profile?.[key] || profile?.user_metadata?.[key];
    if (value) return String(value);
  }
  return '';
}

async function existingGuestSubject(request, env) {
  try {
    const identity = await currentUser(request, env);
    return identity.auth_type === 'guest' ? identity.subject_id : '';
  } catch {
    return '';
  }
}

async function deterministicSubject(environmentId, cloudBaseUid) {
  const digest = new Uint8Array(await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(`${environmentId}:${cloudBaseUid}`),
  ));
  // UUID-shaped stable fallback keeps the existing SQL/user contract valid.
  digest[6] = (digest[6] & 0x0f) | 0x50;
  digest[8] = (digest[8] & 0x3f) | 0x80;
  const hex = Array.from(digest.slice(0, 16), (byte) => byte.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

async function resolveFlorisIdentity(config, accessToken, profile, guestSubject) {
  const fallbackSubject = await deterministicSubject(config.environmentId, profile.sub);
  const candidate = /^[0-9a-f-]{36}$/i.test(guestSubject) ? guestSubject : fallbackSubject;
  try {
    const response = await fetch(
      `${config.gatewayOrigin}/v1/rdb/rest/rpc/bind_cloudbase_identity`,
      {
        method: 'POST',
        redirect: 'error',
        headers: {
          Accept: 'application/json',
          Authorization: `Bearer ${accessToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          p_candidate_user_id: candidate,
          p_display_name: profileText(profile, 'name', 'username').slice(0, 120),
          p_avatar_url: profileText(profile, 'picture', 'avatar_url').slice(0, 1000),
        }),
      },
    );
    const payload = await response.json().catch(() => []);
    const rows = Array.isArray(payload) ? payload : payload?.data;
    if (response.ok && Array.isArray(rows) && rows[0]?.user_id) {
      return {
        subject: String(rows[0].user_id),
        membership: String(rows[0].membership || 'free'),
        roles: Array.isArray(rows[0].roles) ? rows[0].roles : ['user'],
        persisted: true,
      };
    }
  } catch {
    // The authenticated profile is still authoritative. Persistence is an
    // optional enhancement and must not turn login into a hard dependency.
  }
  // Login remains available before the optional SQL migration is applied.
  // The stable CloudBase-derived UUID prevents cross-device identity drift.
  return {
    subject: fallbackSubject,
    membership: 'free',
    roles: ['user'],
    persisted: false,
  };
}

export async function handleCloudBaseSession(context) {
  const { request, env = {} } = context;
  if (request.method !== 'POST') return jsonView({ error: 'Method not allowed' }, 405);
  if (!sameOriginRequest(request)) return jsonView({ error: 'Invalid request origin' }, 403);
  try {
    const config = cloudBaseConfig(env);
    const accessToken = accessTokenFrom(await request.json().catch(() => ({})));
    const [profile, guestSubject] = await Promise.all([
      cloudBaseProfile(config, accessToken),
      existingGuestSubject(request, env),
    ]);
    const resolved = await resolveFlorisIdentity(
      config,
      accessToken,
      profile,
      guestSubject,
    );
    const providers = providerNames(profile);
    const payload = {
      sub: resolved.subject,
      cloudbase_uid: String(profile.sub),
      tenant_id: String(env.DEFAULT_TENANT_ID || 'floris'),
      username: profileText(profile, 'username', 'name', 'email').slice(0, 80)
        || 'cloudbase-user',
      display_name: profileText(profile, 'name', 'username', 'email').slice(0, 120)
        || 'Floris 用户',
      avatar_url: profileText(profile, 'picture', 'avatar_url').slice(0, 1000),
      auth_type: 'cloudbase',
      auth_providers: providers,
      membership: resolved.membership,
      roles: resolved.roles,
      session_version: 1,
    };
    const identity = publicIdentity(payload);
    const token = await signSessionToken(payload, env, USER_SESSION_TTL_SECONDS);
    return jsonView({
      ok: true,
      identity,
      identity_persisted: resolved.persisted,
    }, 200, {
      'Set-Cookie': sessionCookie(token, { maxAge: USER_SESSION_TTL_SECONDS }),
    });
  } catch (error) {
    if (error instanceof AuthError) {
      return jsonView({ error: error.message, code: error.code }, 401);
    }
    return jsonView({ error: 'CloudBase session exchange failed' }, 502);
  }
}
