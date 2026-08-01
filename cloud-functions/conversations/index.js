import { getStore } from '@edgeone/pages-blob';
import { conversationIndexUserId, currentUser, scopedConversationId } from '../../auth/current-user.js';
import {
  listUserConversations,
  touchConversationPointer,
  writeConversationPointer,
} from '../conversation-index.js';

const CONVERSATION_PREFIX = 'yb7_';

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
    conversationId: String(metadata.client_conversation_id || item?.conversationId || ''),
    createdAt,
    lastMessageAt: timestampMs(item?.lastMessageAt, createdAt),
    messageCount: Number(item?.messageCount || 0),
    metadata: {
      title: String(metadata.title || '历史对话'),
      ...(metadata.yuanbao_chat_run_v1
        ? { yuanbao_chat_run_v1: metadata.yuanbao_chat_run_v1 }
        : {}),
    },
  };
}

export async function onRequest(context) {
  const { request, env = {} } = context;
  const store = context.agent?.store;
  if (!store) return json({ error: 'Makers conversation store is unavailable' }, 503);
  let user;
  try {
    user = await currentUser(request, env);
  } catch {
    return json({ error: 'Unauthorized' }, 401);
  }

  if (request.method === 'GET') {
    const indexStore = context.__indexStore || getStore({ name: 'yuanbao-files', consistency: 'strong' });
    const items = await listUserConversations(store, user, { indexStore });
    const conversations = items
      .map(publicConversation)
      .filter((item) => item.conversationId.startsWith(CONVERSATION_PREFIX))
      .sort((first, second) => second.lastMessageAt - first.lastMessageAt);
    return json({ conversations });
  }

  if (request.method === 'POST') {
    const body = await request.json().catch(() => ({}));
    if (body.operation === 'touch_pointer') {
      let clientConversationId;
      let conversationId;
      try {
        clientConversationId = normalizeConversationId(body.conversation_id);
        conversationId = await scopedConversationId(user, clientConversationId);
      } catch {
        return json({ error: 'Invalid conversation id' }, 400);
      }
      const indexStore = context.__indexStore || getStore({ name: 'yuanbao-files', consistency: 'strong' });
      const pointer = await touchConversationPointer(indexStore, user, {
        conversationId,
        clientConversationId,
        title: String(body.title || '').trim() ? titleFromMessage(body.title) : '',
        messageCount: Number(body.message_count || 0),
      });
      return json({ conversation: publicConversation(pointer) });
    }
    if (body.operation !== 'append_message') return json({ error: 'Unsupported conversation operation' }, 400);
    let conversationId;
    let clientConversationId;
    try {
      clientConversationId = normalizeConversationId(body.conversation_id);
      conversationId = await scopedConversationId(user, clientConversationId);
    } catch {
      return json({ error: 'Invalid conversation id' }, 400);
    }
    const content = typeof body.content === 'string' ? body.content : '';
    const role = body.role === 'ai' ? 'assistant' : body.role;
    if (!['user', 'assistant', 'system'].includes(role) || !content) return json({ error: 'Invalid conversation message' }, 400);

    const messageId = await store.appendMessage({
      conversationId, role, content, userId: await conversationIndexUserId(user.id),
      metadata: {
        ...(body.metadata && typeof body.metadata === 'object' ? body.metadata : {}),
        client_message_id: String(body.metadata?.id || ''),
        client_conversation_id: clientConversationId,
        source: 'yuanbao-web',
        owner_user_id: user.id,
        tenant_id: user.tenant_id,
      },
    });
    let conversation = await store.getConversation({ conversationId });
    const currentTitle = String(conversation?.metadata?.title || '');
    if (role === 'user' && (!currentTitle || currentTitle === '新对话' || currentTitle === '历史对话')) {
      conversation = await store.updateConversation({
        conversationId,
        metadata: {
          title: titleFromMessage(content),
          client_conversation_id: clientConversationId,
          owner_user_id: user.id,
          tenant_id: user.tenant_id,
        },
      });
    }
    try {
      const metadata = conversation?.metadata && typeof conversation.metadata === 'object'
        ? conversation.metadata
        : {};
      const indexStore = context.__indexStore || getStore({ name: 'yuanbao-files', consistency: 'strong' });
      await writeConversationPointer(indexStore, user, {
        conversationId,
        clientConversationId,
        createdAt: conversation?.createdAt,
        lastMessageAt: conversation?.lastMessageAt,
        messageCount: conversation?.messageCount,
        metadata,
        title: metadata.title || (role === 'user' ? titleFromMessage(content) : ''),
      });
    } catch {
      // Conversation content remains authoritative; a later save or restore
      // backfills this best-effort sidebar pointer through the same Maker.
    }
    return json({ message_id: messageId, conversation: publicConversation(conversation) });
  }
  return json({ error: 'Method not allowed' }, 405);
}

export const __test = {
  publicConversation,
};
