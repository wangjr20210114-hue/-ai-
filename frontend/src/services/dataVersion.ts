export const DATA_GENERATION = 'v5_20260722_clean';
export const CONVERSATION_PREFIX = `yuanbao_${DATA_GENERATION}_`;

export function isCurrentConversationId(value: string): boolean {
  return String(value || '').startsWith(CONVERSATION_PREFIX);
}
