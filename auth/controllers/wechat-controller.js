import { upsertWechatIdentity } from '../identity-repository.js';
import {
  clearOAuthNonceCookie,
  currentUser,
  oauthNonceCookie,
  publicIdentity,
  readOAuthNonce,
  sessionCookie,
  signSessionToken,
  verifySessionToken,
} from '../session.js';
import { jsonView, redirectView } from '../views/http.js';

const USER_SESSION_TTL_SECONDS = 12 * 60 * 60;

function safeReturnPath(value) {
  const path = String(value || '/chatBot');
  return path.startsWith('/') && !path.startsWith('//')
    ? path.slice(0, 500)
    : '/chatBot';
}

async function wechatJson(url) {
  const response = await fetch(url, {
    headers: { Accept: 'application/json' },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.errcode) {
    throw new Error(`WeChat OAuth failed: ${data.errmsg || response.status}`);
  }
  return data;
}

export async function handleWechatStart(context) {
  const { request, env = {} } = context;
  if (request.method !== 'GET') {
    return jsonView({ error: 'Method not allowed' }, 405);
  }
  const appId = String(env.WECHAT_OPEN_APP_ID || '').trim();
  if (!appId) {
    return jsonView({ error: 'WECHAT_OPEN_APP_ID is not configured' }, 503);
  }
  const url = new URL(request.url);
  const nonce = crypto.randomUUID();
  const returnTo = safeReturnPath(url.searchParams.get('return_to'));
  let guestSubject = '';
  try {
    const current = await currentUser(request, env);
    if (current.auth_type === 'guest') guestSubject = current.subject_id;
  } catch {
    // /auth/session normally creates the guest before this redirect.
  }
  const state = await signSessionToken({
    purpose: 'wechat_oauth_state',
    nonce,
    return_to: returnTo,
    guest_subject: guestSubject,
  }, env, 600);
  const callbackUrl = String(
    env.WECHAT_OPEN_CALLBACK_URL
    || `${url.origin}/auth/wechat/callback`,
  );
  const authorization = new URL('https://open.weixin.qq.com/connect/qrconnect');
  authorization.searchParams.set('appid', appId);
  authorization.searchParams.set('redirect_uri', callbackUrl);
  authorization.searchParams.set('response_type', 'code');
  authorization.searchParams.set('scope', 'snsapi_login');
  authorization.searchParams.set('state', state);
  return redirectView(`${authorization.toString()}#wechat_redirect`, 302, {
    'Set-Cookie': oauthNonceCookie(nonce),
  });
}

export async function handleWechatCallback(context) {
  const { request, env = {} } = context;
  if (request.method !== 'GET') {
    return jsonView({ error: 'Method not allowed' }, 405);
  }
  const url = new URL(request.url);
  const code = String(url.searchParams.get('code') || '').trim();
  const stateToken = String(url.searchParams.get('state') || '').trim();
  if (!code || !stateToken) {
    return jsonView({ error: 'Missing WeChat OAuth code or state' }, 400);
  }
  let state;
  try {
    state = await verifySessionToken(
      stateToken,
      env,
      { purpose: 'wechat_oauth_state' },
    );
  } catch {
    return jsonView({ error: 'Invalid or expired WeChat OAuth state' }, 401);
  }
  if (!state.nonce || state.nonce !== readOAuthNonce(request)) {
    return jsonView({ error: 'WeChat OAuth browser state mismatch' }, 401);
  }
  const appId = String(env.WECHAT_OPEN_APP_ID || '').trim();
  const appSecret = String(env.WECHAT_OPEN_APP_SECRET || '').trim();
  if (!appId || !appSecret) {
    return jsonView({ error: 'WeChat login is not configured' }, 503);
  }
  try {
    const tokenUrl = new URL('https://api.weixin.qq.com/sns/oauth2/access_token');
    tokenUrl.searchParams.set('appid', appId);
    tokenUrl.searchParams.set('secret', appSecret);
    tokenUrl.searchParams.set('code', code);
    tokenUrl.searchParams.set('grant_type', 'authorization_code');
    const oauth = await wechatJson(tokenUrl);
    const profileUrl = new URL('https://api.weixin.qq.com/sns/userinfo');
    profileUrl.searchParams.set('access_token', String(oauth.access_token || ''));
    profileUrl.searchParams.set('openid', String(oauth.openid || ''));
    profileUrl.searchParams.set('lang', 'zh_CN');
    const profile = await wechatJson(profileUrl);
    const user = await upsertWechatIdentity(env, {
      ...profile,
      unionid: profile.unionid || oauth.unionid,
      openid: profile.openid || oauth.openid,
    }, {
      preferredUserId: state.guest_subject,
    });
    const payload = {
      sub: user.user_id,
      tenant_id: user.tenant_id,
      username: user.display_name,
      display_name: user.display_name,
      avatar_url: user.avatar_url,
      auth_type: 'wechat',
      membership: user.membership || 'free',
      roles: Array.isArray(user.roles) && user.roles.length
        ? user.roles
        : ['user'],
      session_version: Number(user.session_version || 1),
    };
    const token = await signSessionToken(
      payload,
      env,
      USER_SESSION_TTL_SECONDS,
    );
    const identity = publicIdentity(payload);
    const headers = new Headers({
      Location: safeReturnPath(state.return_to),
      'Cache-Control': 'no-store',
      'X-Floris-Identity': identity.auth_type,
    });
    headers.append(
      'Set-Cookie',
      sessionCookie(token, { maxAge: USER_SESSION_TTL_SECONDS }),
    );
    headers.append('Set-Cookie', clearOAuthNonceCookie());
    return new Response(null, { status: 302, headers });
  } catch (error) {
    return jsonView({
      error: String(error?.message || 'WeChat login failed'),
    }, 502);
  }
}
