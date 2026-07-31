import { requestJson } from '../../../shared/transport/httpClient';
import { streamEvents, type StreamEventHandlers } from '../../../shared/transport/sseClient';


export const routes = Object.freeze(['/chat', '/conversation', '/messages', '/stop']);

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
