import {
  streamChat,
} from '../model/client';
import type { ChatControllerEvent } from '../model/events';


export function runChatTransport(
  conversationId: string,
  body: unknown,
  receive: (event: ChatControllerEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return streamChat(
    conversationId,
    body,
    { onEvent: (event) => receive(event as ChatControllerEvent) },
    signal,
  );
}
