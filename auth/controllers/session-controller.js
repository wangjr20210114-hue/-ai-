import {
  AuthError,
  clearSessionCookie,
  publicIdentity,
  readBearerToken,
  readSessionToken,
  sessionCookie,
  signSessionToken,
  verifySessionToken,
} from '../session.js';
import { applyProfile, loadProfile } from '../profile.js';
import { publicEntitlements } from '../entitlements.js';
import { jsonView } from '../views/http.js';
import { currentWechatLoginConfig } from '../wechat-config.js';

const GUEST_TTL_SECONDS = 7 * 24 * 60 * 60;
const USER_TTL_SECONDS = 30 * 24 * 60 * 60;
const USER_RENEW_WINDOW_SECONDS = 7 * 24 * 60 * 60;

function sessionFailureView(error) {
  if (error instanceof AuthError && error.code === 'AUTH_NOT_CONFIGURED') {
    return jsonView({
      error: 'Authentication is not configured',
      code: error.code,
    }, 503);
  }
  return jsonView({ error: 'Unable to create guest session' }, 500);
}

function sessionView(identity, request, env, headers = {}) {
  const wechat = currentWechatLoginConfig(request, env);
  return jsonView({
    identity,
    entitlements: publicEntitlements(identity),
    login: {
      cloudbase_available: true,
      cloudbase_session_url: '/auth/cloudbase/session',
      wechat_available: wechat.available,
      wechat_mode: wechat.mode,
      wechat_start_url: '/auth/wechat/start',
      logout_url: '/auth/logout',
    },
  }, 200, headers);
}

export async function handleSession(context) {
  const { request, env = {} } = context;
  if (request.method !== 'GET') {
    return jsonView({ error: 'Method not allowed' }, 405);
  }
  try {
    const token = readSessionToken(request.headers);
    if (!token) throw new AuthError('Authentication session is required');
    const payload = await verifySessionToken(token, env);
    let identity = publicIdentity(payload);
    identity = applyProfile(
      identity,
      await loadProfile(context.profileStore, identity),
    );
    const now = Math.floor(Date.now() / 1000);
    const shouldRenew = !readBearerToken(request.headers)
      && identity.auth_type !== 'guest'
      && Number(payload.exp || 0) - now <= USER_RENEW_WINDOW_SECONDS;
    if (!shouldRenew) return sessionView(identity, request, env);
    const renewedPayload = {
      ...payload,
      display_name: identity.display_name,
      avatar_url: identity.avatar_url,
    };
    const renewed = await signSessionToken(renewedPayload, env, USER_TTL_SECONDS);
    return sessionView(identity, request, env, {
      'Set-Cookie': sessionCookie(renewed, { maxAge: USER_TTL_SECONDS }),
    });
  } catch (error) {
    if (!(error instanceof AuthError)) {
      return sessionFailureView(error);
    }
    // An API client that explicitly supplied an expired or invalid Bearer must
    // refresh through CloudBase. Never silently turn it into a browser guest.
    if (readBearerToken(request.headers)) {
      return jsonView({
        error: 'Authentication session is invalid or expired',
        code: 'UNAUTHORIZED',
      }, 401);
    }
  }
  try {
    const payload = {
      sub: crypto.randomUUID(),
      tenant_id: String(env.DEFAULT_TENANT_ID || 'floris'),
      username: 'guest',
      display_name: '游客',
      avatar_url: '',
      auth_type: 'guest',
      membership: 'guest',
      roles: ['guest'],
      session_version: 1,
    };
    const token = await signSessionToken(payload, env, GUEST_TTL_SECONDS);
    return sessionView(publicIdentity(payload), request, env, {
      'Set-Cookie': sessionCookie(token, { maxAge: GUEST_TTL_SECONDS }),
    });
  } catch (error) {
    return sessionFailureView(error);
  }
}

export const sessionDurations = Object.freeze({
  guest: GUEST_TTL_SECONDS,
  authenticated: USER_TTL_SECONDS,
  renewWindow: USER_RENEW_WINDOW_SECONDS,
});

export async function handleLogout(context) {
  if (context.request.method !== 'POST') {
    return jsonView({ error: 'Method not allowed' }, 405);
  }
  return jsonView({ ok: true }, 200, {
    'Set-Cookie': clearSessionCookie(),
  });
}
