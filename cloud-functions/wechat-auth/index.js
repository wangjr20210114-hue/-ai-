import { createHmac } from 'node:crypto';
import {
  conversationPrefixForUser,
  signMiniappSession,
} from '../../auth/current-user.js';

const SESSION_TTL_MS = 7 * 24 * 60 * 60 * 1000;

const json = (data, status = 200) => new Response(JSON.stringify(data), {
  status,
  headers: {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
  },
});

function userIdForOpenId(openid, secret) {
  const digest = createHmac('sha256', secret).update(String(openid)).digest('hex').slice(0, 24);
  return `wx_${digest}`;
}

export async function onRequest(context) {
  const { request, env = {} } = context;
  if (request.method !== 'POST') return json({ error: 'Method not allowed' }, 405);
  const appId = String(env.WECHAT_MINIAPP_APP_ID || '').trim();
  const appSecret = String(env.WECHAT_MINIAPP_APP_SECRET || '').trim();
  const sessionSecret = String(env.MINIAPP_SESSION_SECRET || '').trim();
  if (!appId || !appSecret || !sessionSecret) {
    return json({ error: '微信登录尚未配置' }, 503);
  }
  const body = await request.json().catch(() => ({}));
  const code = String(body?.code || '').trim();
  if (!code || code.length > 256) return json({ error: '无效的微信登录凭证' }, 400);

  const endpoint = new URL('https://api.weixin.qq.com/sns/jscode2session');
  endpoint.search = new URLSearchParams({
    appid: appId,
    secret: appSecret,
    js_code: code,
    grant_type: 'authorization_code',
  }).toString();
  const exchange = await (context.fetch || fetch)(endpoint);
  const result = await exchange.json().catch(() => ({}));
  if (!exchange.ok || !result.openid || result.errcode) {
    return json({
      error: '微信登录失败，请重试',
      code: String(result.errcode || exchange.status || 'WECHAT_LOGIN_FAILED'),
    }, 401);
  }

  const userId = userIdForOpenId(result.openid, sessionSecret);
  const expiresAt = Date.now() + SESSION_TTL_MS;
  const token = signMiniappSession({ userId, expiresAt }, sessionSecret);
  return json({
    token,
    expires_at: expiresAt,
    user_id: userId,
    conversation_prefix: conversationPrefixForUser(userId),
  });
}
