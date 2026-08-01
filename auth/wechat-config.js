export const WECHAT_LOGIN_MODE_QR = 'qr';
export const WECHAT_LOGIN_MODE_IN_APP = 'in_app';

const LOGIN_MODES = new Set([
  WECHAT_LOGIN_MODE_QR,
  WECHAT_LOGIN_MODE_IN_APP,
]);

function envValue(env, key) {
  return String(env?.[key] || '').trim();
}

export function isWechatBrowser(request) {
  const userAgent = String(request?.headers?.get?.('user-agent') || '');
  return /MicroMessenger/i.test(userAgent);
}

export function normalizeWechatLoginMode(value) {
  const mode = String(value || '').trim();
  return LOGIN_MODES.has(mode) ? mode : '';
}

export function currentWechatLoginMode(request) {
  return isWechatBrowser(request)
    ? WECHAT_LOGIN_MODE_IN_APP
    : WECHAT_LOGIN_MODE_QR;
}

export function resolveWechatLoginConfig(env, { mode, origin } = {}) {
  const resolvedMode = normalizeWechatLoginMode(mode);
  if (!resolvedMode) throw new Error('Invalid WeChat login mode');

  const callbackFallback = `${String(origin || '').replace(/\/$/, '')}/auth/wechat/callback`;
  const databaseReady = Boolean(envValue(env, 'DATABASE_URL'));
  if (resolvedMode === WECHAT_LOGIN_MODE_IN_APP) {
    const appId = envValue(env, 'WECHAT_OFFICIAL_ACCOUNT_APP_ID');
    const appSecret = envValue(env, 'WECHAT_OFFICIAL_ACCOUNT_APP_SECRET');
    return {
      mode: resolvedMode,
      appId,
      appSecret,
      callbackUrl: envValue(env, 'WECHAT_OFFICIAL_ACCOUNT_CALLBACK_URL')
        || callbackFallback,
      authorizationEndpoint: 'https://open.weixin.qq.com/connect/oauth2/authorize',
      scope: 'snsapi_userinfo',
      available: Boolean(databaseReady && appId && appSecret),
    };
  }

  const appId = envValue(env, 'WECHAT_OPEN_APP_ID');
  const appSecret = envValue(env, 'WECHAT_OPEN_APP_SECRET');
  return {
    mode: resolvedMode,
    appId,
    appSecret,
    callbackUrl: envValue(env, 'WECHAT_OPEN_CALLBACK_URL') || callbackFallback,
    authorizationEndpoint: 'https://open.weixin.qq.com/connect/qrconnect',
    scope: 'snsapi_login',
    available: Boolean(databaseReady && appId && appSecret),
  };
}

export function currentWechatLoginConfig(request, env) {
  return resolveWechatLoginConfig(env, {
    mode: currentWechatLoginMode(request),
    origin: new URL(request.url).origin,
  });
}
