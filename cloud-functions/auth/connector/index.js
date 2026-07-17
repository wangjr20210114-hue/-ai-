import { createHash, randomBytes } from 'node:crypto';
import { requireAuth } from '../../_jwt.js';
import { updateConnectorHash } from '../../_db.js';

const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' } });

export async function onRequestPost({ request, env }) {
  try {
    const user = await requireAuth({ request, env });
    const operation = new URL(request.url).searchParams.get('operation') || 'rotate';
    if (operation === 'revoke') { await updateConnectorHash(env, user.sub, null); return json({ ok: true }); }
    const token = `ybp_${randomBytes(32).toString('base64url')}`;
    await updateConnectorHash(env, user.sub, createHash('sha256').update(token).digest('base64url'));
    return json({ ok: true, connector_secret: token });
  } catch { return json({ error: 'unauthorized' }, 401); }
}
