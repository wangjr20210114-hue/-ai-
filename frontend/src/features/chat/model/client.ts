import { requestJson, requestRaw } from '../../../shared/transport/httpClient';
import { authorizedFetch, withEdgeOneAuth } from '../../../shared/auth/session';
import { streamEvents, type StreamEventHandlers } from '../../../shared/transport/sseClient';
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
  MakersChatRun,
} from './types';


export const routes = Object.freeze([
  '/chat',
  '/conversation',
  '/conversations',
  '/files',
  '/messages',
  '/stop',
]);

export function loadMessages<T>(conversationId: string): Promise<T> {
  return requestJson<T>('/messages', {
    headers: { 'makers-conversation-id': conversationId },
  });
}

export function appendConversationMessage<T>(
  conversationId: string,
  message: unknown,
): Promise<T> {
  return requestJson<T>('/conversation', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'makers-conversation-id': conversationId,
    },
    body: JSON.stringify({ message }),
  });
}

export function stopConversation<T>(conversationId: string): Promise<T> {
  return requestJson<T>('/stop', {
    method: 'POST',
    headers: { 'makers-conversation-id': conversationId },
  });
}

export function streamChat(
  conversationId: string,
  body: unknown,
  handlers: StreamEventHandlers,
  signal?: AbortSignal,
): Promise<void> {
  return streamEvents('/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'makers-conversation-id': conversationId,
    },
    body: JSON.stringify(body),
  }, handlers, signal);
}

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
  signal?: AbortSignal,
): Promise<Response> {
  return authorizedFetch('/stop', {
    method: 'POST',
    // Makers requires cancellation to target the run through the payload.
    // Carrying the conversation header can replace the active run signal.
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conversation_id: conversationId }),
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
      throw new Error(`Could not load Makers run (${response.status})`);
    }
  } catch (error) {
    if (options.strict) throw error;
  } finally {
    window.clearTimeout(timeout);
    options.signal?.removeEventListener('abort', abortFromCaller);
  }
  return { messages: [] };
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
  return {
    id,
    title: String(metadata.title || item.title || translate('newConversation')),
    createdAt,
    updatedAt,
    messageCount: Number(item.messageCount || item.message_count || 0),
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
): Promise<StoredFileInfo> {
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
  const stored = await requestRaw(upload.url, {
    method: 'PUT',
    headers: { 'Content-Type': file.type || 'application/pdf' },
    body: file,
  }, false);
  if (!stored.ok) throw new Error(translate('blobUploadFailed'));
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
