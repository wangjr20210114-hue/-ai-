import type { ChatMessage } from '../model/types';


export interface ConversationLifecycle {
  conversationId: string;
  messages: ChatMessage[];
  interrupted: boolean;
}

export function restoreConversation(
  conversationId: string,
  messages: ChatMessage[],
  runActive: boolean,
): ConversationLifecycle {
  const tail = messages[messages.length - 1];
  return {
    conversationId,
    messages,
    interrupted: Boolean(runActive || tail?.role === 'user'),
  };
}
