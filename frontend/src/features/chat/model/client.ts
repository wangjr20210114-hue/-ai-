import {
  requestJson,
  requestRaw,
  uploadRawWithProgress,
} from '../../../shared/transport/httpClient';
import { authorizedFetch, withEdgeOneAuth } from '../../../shared/auth/session';
import { translate } from '../../../i18n';
import {
  createConversationId,
  makersConversationHeaders,
} from '../../../services/conversation';
import { isCurrentConversationId } from '../../../services/dataVersion';
import { normalizeTimestamp } from '../../../services/time';
import type {
  ChatMessage,
  ConversationSummary,
  StoredFileInfo,
} from './types';
import type {
  BootstrapData,
  BootstrapOptions,
  ChatRunState,
  MakersChatRun,
} from './types';


export const routes = Object.freeze([
  '/chat',
  '/conversation',
  '/conversations',
  '/files',
  '/messages',
  '/run',
  '/stop',
]);

export function openChatTurn(
  conversationId: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<Response> {
  return authorizedFetch('/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...makersConversationHeaders(conversationId),
    },
    body: JSON.stringify(body),
    signal,
  });
}

export function requestConversationStop(
  conversationId: string,
  clientMessageId = '',
  signal?: AbortSignal,
): Promise<Response> {
  return authorizedFetch('/stop', {
    method: 'POST',
    // Maker middleware scopes every conversation operation from this header;
    // the exact client turn remains in the payload so a delayed stop cannot
    // cancel a newer FIFO head.
    headers: {
      'Content-Type': 'application/json',
      ...makersConversationHeaders(conversationId),
    },
    body: JSON.stringify({
      conversation_id: conversationId,
      ...(clientMessageId ? { client_message_id: clientMessageId } : {}),
    }),
    signal,
  });
}

export async function bootstrapApp(
  conversationId: string,
  options: BootstrapOptions = {},
): Promise<BootstrapData> {
  const controller = new AbortController();
  const abortFromCaller = () => controller.abort();
  options.signal?.addEventListener('abort', abortFromCaller, { once: true });
  const timeout = window.setTimeout(
    () => controller.abort(),
    Math.max(1000, options.timeoutMs ?? 8000),
  );
  try {
    const response = await authorizedFetch('/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'makers-conversation-id': conversationId,
      },
      body: JSON.stringify({ conversation_id: conversationId }),
      signal: controller.signal,
    });
    if (response.ok) {
      const data = await response.json() as BootstrapData;
      const messages = Array.isArray(data.messages) ? data.messages : [];
      const firstUser = messages.find((item) => item?.role === 'user');
      if (messages.length) {
        void touchConversationIndex(
          conversationId,
          typeof firstUser?.content === 'string' ? firstUser.content : '',
          messages.length,
        ).catch(() => {});
      }
      return data;
    }
    if (options.strict) {
      throw new Error(translate('chatRunLoadFailed', { status: response.status }));
    }
  } catch (error) {
    if (options.strict) throw error;
  } finally {
    window.clearTimeout(timeout);
    options.signal?.removeEventListener('abort', abortFromCaller);
  }
  return { messages: [] };
}

export function readChatRun(
  conversationId: string,
  signal?: AbortSignal,
): Promise<ChatRunState> {
  return requestJson<ChatRunState>('/run', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...makersConversationHeaders(conversationId),
    },
    body: JSON.stringify({ conversation_id: conversationId }),
    signal,
  });
}

function normalizeConversation(
  item: Record<string, unknown>,
): ConversationSummary {
  const metadata = item.metadata && typeof item.metadata === 'object'
    ? item.metadata as Record<string, unknown>
    : {};
  const id = String(item.conversationId || item.id || '');
  const createdAt = normalizeTimestamp(item.createdAt ?? item.created_at);
  const updatedAt = normalizeTimestamp(
    item.lastMessageAt ?? item.updatedAt ?? item.updated_at,
    createdAt,
  );
  const run = metadata.yuanbao_chat_run_v1
    && typeof metadata.yuanbao_chat_run_v1 === 'object'
    ? metadata.yuanbao_chat_run_v1 as MakersChatRun
    : null;
  const activityStatus = run?.status === 'running'
    || run?.status === 'cancel_requested'
    ? 'running'
    : run?.status === 'failed' ? 'failed' : 'idle';
  const messageCount = Number(item.messageCount || item.message_count || 0);
  return {
    id,
    title: String(metadata.title || item.title || translate('newConversation')),
    createdAt,
    updatedAt,
    messageCount,
    pending: messageCount === 0,
    activityStatus,
  };
}

export async function listConversations(): Promise<ConversationSummary[]> {
  const data = await requestJson<{
    conversations?: Record<string, unknown>[];
  }>('/conversations');
  return (data.conversations || [])
    .map(normalizeConversation)
    .filter((item) => item.id && isCurrentConversationId(item.id))
    .sort((a, b) => b.updatedAt - a.updatedAt);
}

export function createNewConversation(): ConversationSummary {
  const now = Date.now();
  return {
    id: createConversationId(),
    title: translate('newConversation'),
    createdAt: now,
    updatedAt: now,
    messageCount: 0,
    pending: true,
  };
}

export async function touchConversationIndex(
  conversationId: string,
  title = '',
  messageCount = 0,
): Promise<void> {
  await requestJson('/conversations', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...makersConversationHeaders(conversationId),
    },
    body: JSON.stringify({
      operation: 'touch_pointer',
      conversation_id: conversationId,
      title,
      message_count: messageCount,
    }),
  });
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('yuanbao:conversation-saved', {
      detail: { conversationId },
    }));
  }
}

export async function renameConversation(
  conversationId: string,
  title: string,
): Promise<ConversationSummary> {
  const data = await requestJson<{ conversation?: Record<string, unknown> }>('/conversations', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...makersConversationHeaders(conversationId),
    },
    body: JSON.stringify({
      operation: 'rename',
      conversation_id: conversationId,
      title: title.trim(),
    }),
  });
  if (!data.conversation) throw new Error(translate('renameConversationFailed'));
  return normalizeConversation(data.conversation);
}

export async function saveConversationMessage(
  conversationId: string,
  message: ChatMessage,
): Promise<void> {
  await requestJson('/conversation', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...makersConversationHeaders(conversationId),
    },
    body: JSON.stringify({
      role: message.role,
      content: message.content,
      metadata: message,
    }),
  });
  if (message.role === 'user') {
    await touchConversationIndex(conversationId, message.content, 1);
    return;
  }
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('yuanbao:conversation-saved', {
      detail: { conversationId },
    }));
  }
}

export async function uploadDocument(
  conversationId: string,
  file: File,
  onProgress?: (percent: number) => void,
): Promise<StoredFileInfo> {
  onProgress?.(0);
  const upload = await requestJson<{
    url?: string;
    key?: string;
    content_url?: string;
  }>('/files', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      conversation_id: conversationId,
      name: file.name,
      content_type: file.type || 'application/pdf',
      size: file.size,
    }),
  });
  if (!upload.url || !upload.key) throw new Error(translate('blobUploadUrlFailed'));
  onProgress?.(4);
  const stored = await uploadBlobWithProgress(
    upload.url,
    file,
    file.type || 'application/pdf',
    onProgress,
  );
  if (!stored.ok) throw new Error(translate('blobUploadFailed'));
  onProgress?.(100);
  return {
    id: upload.key,
    original_name: file.name,
    mime_type: file.type || 'application/pdf',
    size_bytes: file.size,
    page_count: 0,
    total_chars: 0,
    preview: translate('blobSavedPreview'),
    created_at: Date.now(),
    storage_key: upload.key,
    content_url: upload.content_url
      ? withEdgeOneAuth(upload.content_url)
      : undefined,
  };
}

function uploadBlobWithProgress(
  url: string,
  file: File,
  contentType: string,
  onProgress?: (percent: number) => void,
): Promise<Response> {
  if (!onProgress) {
    return requestRaw(url, {
      method: 'PUT',
      headers: { 'Content-Type': contentType },
      body: file,
    }, false);
  }
  return uploadRawWithProgress(url, file, contentType, (percent) => {
    onProgress(Math.min(99, Math.max(4, Math.round(4 + percent * 0.95))));
  });
}
