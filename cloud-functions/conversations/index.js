const USER_ID = 'local-user';

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
}

function titleFromMessage(content) {
  const title = String(content || '')
    .replace(/\s+/g, ' ')
    .replace(/^[#>*`\-\s]+/, '')
    .trim();
  if (!title) return '新对话';
  return title.length > 32 ? `${title.slice(0, 32)}…` : title;
}

function publicConversation(item) {
  const metadata = item?.metadata && typeof item.metadata === 'object' ? item.metadata : {};
  return {
    conversationId: String(item?.conversationId || ''),
    createdAt: Number(item?.createdAt || Date.now()),
    lastMessageAt: Number(item?.lastMessageAt || item?.createdAt || Date.now()),
    messageCount: Number(item?.messageCount || 0),
    metadata: {
      ...metadata,
      title: String(metadata.title || '历史对话'),
    },
  };
}

export async function onRequest(context) {
  const { request } = context;
  const store = context.agent?.store;
  if (!store) return json({ error: 'Makers conversation store is unavailable' }, 503);

  if (request.method === 'GET') {
    const result = await store.listConversations({ limit: 100, order: 'desc' });
    const items = Array.isArray(result?.items) ? result.items : [];
    return json({ conversations: items.map(publicConversation) });
  }

  if (request.method === 'POST') {
    const body = await request.json().catch(() => ({}));
    if (body.operation !== 'append_message') {
      return json({ error: 'Unsupported conversation operation' }, 400);
    }

    const conversationId = String(body.conversation_id || '').trim();
    const content = typeof body.content === 'string' ? body.content : '';
    const role = body.role === 'ai' ? 'assistant' : body.role;
    if (!conversationId || conversationId.length > 256) {
      return json({ error: 'Invalid conversation id' }, 400);
    }
    if (!['user', 'assistant', 'system'].includes(role) || !content) {
      return json({ error: 'Invalid conversation message' }, 400);
    }

    const messageId = await store.appendMessage({
      conversationId,
      role,
      content,
      metadata: {
        ...(body.metadata && typeof body.metadata === 'object' ? body.metadata : {}),
        client_message_id: String(body.metadata?.id || ''),
        source: 'yuanbao-web',
      },
      userId: USER_ID,
    });

    let conversation = await store.getConversation({ conversationId });
    const currentTitle = String(conversation?.metadata?.title || '');
    if (role === 'user' && (!currentTitle || currentTitle === '新对话' || currentTitle === '历史对话')) {
      conversation = await store.updateConversation({
        conversationId,
        metadata: { title: titleFromMessage(content), user_id: USER_ID },
      });
    }
    return json({ message_id: messageId, conversation: publicConversation(conversation) });
  }

  return json({ error: 'Method not allowed' }, 405);
}
