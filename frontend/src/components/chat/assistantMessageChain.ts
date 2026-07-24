import type { ChatMessage } from '../../types';

export type AssistantChainPosition = 'single' | 'start' | 'middle' | 'end';

/**
 * A clarification answer is deliberately hidden from the visible transcript:
 * it resumes the same Agent turn instead of becoming a new user message.
 * Consecutive assistant checkpoints therefore belong to one visible answer.
 *
 * Keep the checkpoint records separate for Makers-native restoration, and
 * describe only how the frontend should join them visually.
 */
export function assistantChainPositions(
  messages: ReadonlyArray<Pick<ChatMessage, 'role'>>,
): AssistantChainPosition[] {
  return messages.map((message, index) => {
    if (message.role !== 'ai') return 'single';
    const previousIsAssistant = messages[index - 1]?.role === 'ai';
    const nextIsAssistant = messages[index + 1]?.role === 'ai';
    if (previousIsAssistant && nextIsAssistant) return 'middle';
    if (previousIsAssistant) return 'end';
    if (nextIsAssistant) return 'start';
    return 'single';
  });
}
