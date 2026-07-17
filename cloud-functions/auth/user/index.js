import { requireAuth } from '../../_jwt.js';

export async function onRequest({ request, env }) {
  if (String(env.AUTH_MODE || 'single_user') !== 'multi_user') return Response.json({ mode: 'single_user', user: { id: 'local-user', username: 'local-user', roles: ['owner'] } });
  try {
    const payload = await requireAuth({ request, env });
    return Response.json({ mode: 'multi_user', user: { id: payload.sub, username: payload.username, roles: payload.roles || ['user'] } });
  } catch { return Response.json({ error: 'unauthorized' }, { status: 401 }); }
}
