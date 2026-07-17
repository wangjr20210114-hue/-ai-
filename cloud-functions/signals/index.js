import { getStore } from '@edgeone/pages-blob';
import { createHash } from 'node:crypto';
import { findConnectorUser } from '../_db.js';
const ALLOWED_TYPES = new Set(['calendar_event', 'calendar_changed', 'email_received', 'enterprise_message', 'file_uploaded']);

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' } });
}

export async function onRequest({ request, env }) {
  if (request.method !== 'POST') return json({ error: 'Method not allowed' }, 405);
  if (String(env.AUTH_MODE || 'single_user') !== 'multi_user') return json({ error: 'Per-user connectors require multi_user mode' }, 503);
  if (String(env.PROACTIVE_SCHEDULE_SECRET || '').length < 32) return json({ error: 'Connector bridge is not configured' }, 503);
  const authorization = request.headers.get('authorization') || '';
  const token = authorization.startsWith('Bearer ') ? authorization.slice(7).trim() : '';
  if (!/^ybp_[A-Za-z0-9_-]{40,80}$/.test(token)) return json({ error: 'Invalid connector credential' }, 401);
  const user = await findConnectorUser(env, createHash('sha256').update(token).digest('base64url')).catch(() => null);
  if (!user || !/^[0-9a-f-]{16,64}$/i.test(String(user.id || ''))) return json({ error: 'Invalid connector credential' }, 401);
  const body = await request.json().catch(() => ({}));
  const signalType = String(body.signal_type || '');
  if (!ALLOWED_TYPES.has(signalType)) return json({ error: 'Unsupported signal type' }, 400);
  const dedupKey = String(body.dedup_key || '').trim().slice(0, 240);
  if (!dedupKey) return json({ error: 'dedup_key is required' }, 400);
  const target = new URL('/proactive', request.url);
  const result = await fetch(target, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'makers-conversation-id': `yuanbao-connector-${user.id}`,
      'x-yuanbao-user-id': user.id,
      'x-yuanbao-system-secret': String(env.PROACTIVE_SCHEDULE_SECRET || ''),
    },
    body: JSON.stringify({
      operation: 'ingest_signal',
      signal_type: 'external_webhook',
      dedup_key: `${signalType}:${dedupKey}`,
      payload: { source_type: signalType, ...(body.payload && typeof body.payload === 'object' ? body.payload : {}) },
    }),
  });
  const data = await result.json().catch(() => ({ error: `Invalid proactive response: ${result.status}` }));
  return json(data, result.status);
}
