import {
  sessionConstants,
  readCookie,
} from './auth/session.js';

const PUBLIC_PREFIXES = [
  '/auth/session',
  '/auth/wechat/start',
  '/auth/wechat/callback',
  '/auth/logout',
];

export async function middleware(context) {
  const { request, next } = context;
  const path = new URL(request.url).pathname;
  if (PUBLIC_PREFIXES.some((prefix) => path.startsWith(prefix))) return next();
  const token = readCookie(request.headers, sessionConstants.cookieName);
  if (!token) {
    return new Response(JSON.stringify({
      error: 'Authentication session is required',
      code: 'UNAUTHORIZED',
    }), {
      status: 401,
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Cache-Control': 'no-store',
      },
    });
  }
  // Edge middleware is a coarse request gate. Trusted Agent and Cloud
  // Function controllers verify the signature, tenant and entitlements using
  // their own Maker runtime env, avoiding a second environment-dependent HMAC
  // decision before the request reaches its authoritative boundary.
  return next();
}

export const config = {
  matcher: [
    '/chat/:path*',
    '/conversation/:path*',
    '/conversations/:path*',
    '/messages/:path*',
    '/stop/:path*',
    '/intelligence/:path*',
    '/workspace/:path*',
    '/files/:path*',
    '/library/:path*',
    '/papers/:path*',
    '/image/:path*',
    '/places/:path*',
    '/routes/:path*',
    '/proactive/:path*',
    '/provider_usage/:path*',
    '/reader/:path*',
    '/skill_marketplace/:path*',
    '/skill-uploads/:path*',
    '/system/:path*',
    '/system_internal/:path*',
    '/reset/:path*',
    '/reset-files/:path*',
  ],
};
