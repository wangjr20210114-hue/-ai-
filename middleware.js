import { readCookie, verifyToken } from './cloud-functions/_jwt.js';

const unauthorized = (reason) => new Response(JSON.stringify({ error: 'unauthorized', reason }), {
  status: 401,
  headers: { 'Content-Type': 'application/json; charset=utf-8' },
});

export async function middleware({ request, env, next }) {
  if (String(env.AUTH_MODE || 'single_user') !== 'multi_user') return next();
  const systemSecret = request.headers.get('x-yuanbao-system-secret') || '';
  if (systemSecret && systemSecret === String(env.PROACTIVE_SCHEDULE_SECRET || '')) return next();
  try {
    await verifyToken(readCookie(request.headers), env);
    return next();
  } catch (error) {
    return unauthorized(error?.message || 'authentication required');
  }
}

export const config = {
  matcher: [
    '/chat/:path*', '/stop/:path*', '/messages/:path*', '/workspace/:path*',
    '/image/:path*', '/places/:path*', '/routes/:path*', '/reader/:path*',
    '/proactive/:path*', '/intelligence/:path*', '/system/:path*',
    '/conversations/:path*', '/files/:path*', '/library/:path*', '/papers/:path*',
  ],
};
