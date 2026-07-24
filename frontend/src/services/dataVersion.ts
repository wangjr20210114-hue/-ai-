export const CONVERSATION_PREFIX = 'yb7_';

export function isCurrentConversationId(value: string): boolean {
  return String(value || '').startsWith(CONVERSATION_PREFIX);
}
