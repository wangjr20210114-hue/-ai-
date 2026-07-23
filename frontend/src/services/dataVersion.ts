export const DATA_GENERATION = 'v6_20260724_reset';
export const CONVERSATION_PREFIX = 'yb6_';

export function isCurrentConversationId(value: string): boolean {
  return String(value || '').startsWith(CONVERSATION_PREFIX);
}
