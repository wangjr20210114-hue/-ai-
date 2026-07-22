import { currentUser } from '../../auth/current-user.js';

const CONVERSATION_PREFIX = 'yuanbao_v5_20260722_clean_';

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json; charset=utf-8' } });
}

function normalizeConversationId(value) {
  const raw = String(value || '').trim();
  if (!raw || raw.length > 180 || !raw.startsWith(CONVERSATION_PREFIX)) throw new Error('Invalid conversation id');
  return raw;
}

function titleFromMessage(content) {
  const title = String(content || '').replace(/\s+/g, ' ').replace(/^[#>*`\-\s]+/, '').trim();
  if (!title) return '新对话';
  return title.length > 32 ? `${title.slice(0, 32)}…` : title;
}

function timestampMs(value, fallback = Date.now()) {
  const text = typeof value === 'string' ? value.trim() : '';
  const numeric = typeof value === 'number' ? value : text && /^-?\d+(?:\.\d+)?$/.test(text) ? Number(text) : Number.NaN;
  if (Number.isFinite(numeric) && numeric > 0) {
    if (numeric < 100_000_000_000) return Math.round(numeric * 1000);
    if (numeric > 10_000_000_000_000) return Math.round(numeric / 1000);
    return Math.round(numeric);
  }
  const parsed = text ? Date.parse(text) : Number.NaN;
  return Number.isFinite(parsed) ? parsed : fallback;
}

function publicConversation(item) {
  const metadata = item?.metadata && typeof item.metadata === 'object' ? item.metadata : {};
  const createdAt = timestampMs(item?.createdAt);
  return {
    conversationId: String(item?.conversationId || ''),
    createdAt,
    lastMessageAt: timestampMs(item?.lastMessageAt, createdAt),
    messageCount: Number(item?.messageCount || 0),
    metadata: { ...metadata, user_id: undefined, title: String(metadata.title || '历史对话') },
  };
}

export async function onRequest(context) {
  const { request } = context;
  const store = context.agent?.store;
  if (!store) return json({ error: 'Makers conversation store is unavailable' }, 503);
  let user;
  user = await currentUser();

  if (request.method === 'GET') {
    const result = await store.listConversations({ userId: user.id, limit: 100, order: 'desc' });
    const items = Array.isArray(result?.items) ? result.items : [];
    return json({ conversations: items.map(publicConversation).filter((item) => item.conversationId.startsWith(CONVERSATION_PREFIX)) });
  }

  if (request.method === 'POST') {
    const body = await request.json().catch(() => ({}));
    if (body.operation !== 'append_message') return json({ error: 'Unsupported conversation operation' }, 400);
    let conversationId;
    try { conversationId = normalizeConversationId(body.conversation_id); } catch { return json({ error: 'Invalid conversation id' }, 400); }
    const content = typeof body.content === 'string' ? body.content : '';
    const role = body.role === 'ai' ? 'assistant' : body.role;
    if (!['user', 'assistant', 'system'].includes(role) || !content) return json({ error: 'Invalid conversation message' }, 400);

    const messageId = await store.appendMessage({
      conversationId, role, content, userId: user.id,
      metadata: {
        ...(body.metadata && typeof body.metadata === 'object' ? body.metadata : {}),
        client_message_id: String(body.metadata?.id || ''), source: 'yuanbao-web', owner_user_id: user.id,
      },
    });
    let conversation = await store.getConversation({ conversationId });
    const currentTitle = String(conversation?.metadata?.title || '');
    if (role === 'user' && (!currentTitle || currentTitle === '新对话' || currentTitle === '历史对话')) {
      conversation = await store.updateConversation({ conversationId, metadata: { title: titleFromMessage(content), owner_user_id: user.id } });
    }
    return json({ message_id: messageId, conversation: publicConversation(conversation) });
  }
  return json({ error: 'Method not allowed' }, 405);
}
