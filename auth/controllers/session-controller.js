import {
  AuthError,
  clearSessionCookie,
  currentUser,
  publicIdentity,
  sessionCookie,
  signSessionToken,
} from '../session.js';
import { publicEntitlements } from '../entitlements.js';
import { jsonView } from '../views/http.js';

const GUEST_TTL_SECONDS = 7 * 24 * 60 * 60;

function sessionFailureView(error) {
  if (error instanceof AuthError && error.code === 'AUTH_NOT_CONFIGURED') {
    return jsonView({
      error: 'Authentication is not configured',
      code: error.code,
    }, 503);
  }
  return jsonView({ error: 'Unable to create guest session' }, 500);
}

function sessionView(identity, env, headers = {}) {
  return jsonView({
    identity,
    entitlements: publicEntitlements(identity),
    login: {
      wechat_available: Boolean(
        String(env.WECHAT_OPEN_APP_ID || '').trim()
        && String(env.WECHAT_OPEN_APP_SECRET || '').trim()
        && String(env.DATABASE_URL || '').trim(),
      ),
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
    return sessionView(await currentUser(request, env), env);
  } catch (error) {
    if (!(error instanceof AuthError)) {
      return sessionFailureView(error);
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
    return sessionView(publicIdentity(payload), env, {
      'Set-Cookie': sessionCookie(token, { maxAge: GUEST_TTL_SECONDS }),
    });
  } catch (error) {
    return sessionFailureView(error);
  }
}

export async function handleLogout(context) {
  if (context.request.method !== 'POST') {
    return jsonView({ error: 'Method not allowed' }, 405);
  }
  return jsonView({ ok: true }, 200, {
    'Set-Cookie': clearSessionCookie(),
  });
}
