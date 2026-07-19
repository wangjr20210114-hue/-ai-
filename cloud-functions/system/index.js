/** Public /system entry; detailed state stays in the Makers Agent Store. */

import { currentUser } from '../../auth/current-user.js';

const json = (data, status = 200) => new Response(JSON.stringify(data), {
  status,
  headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' },
});

export async function onRequest(context) {
  const { request, env } = context;
  if (request.method !== 'GET') return json({ error: 'Method not allowed' }, 405);
  let user;
  try { user = await currentUser(request, env); } catch { return json({ error: 'Unauthorized' }, 401); }

  if (request.headers.get('makers-conversation-id')) {
    return new Response(null, {
      status: 307,
      headers: { Location: '/system_internal', 'Cache-Control': 'no-store' },
    });
  }
  return json({
    status: 'ok',
    scope: 'public',
    scheduler: { schedule: '0 8 * * *', timezone: 'Asia/Shanghai' },
    observability: '/agent-metrics',
    details: {
      path: '/system_internal',
      requires_header: 'makers-conversation-id',
      note: '详细运行状态由 Makers Agent 从原生 LangGraph Store 读取',
    },
    identity: {
      mode: String(env.AUTH_MODE || 'single_user') === 'multi_user' ? 'multi_user' : 'single_user',
      user_id: user.id,
    },
  });
}
