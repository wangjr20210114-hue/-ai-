import { hasDurableAssistantPayload } from '../../../services/conversation';
import type { ChatMessage, WorkspaceAction } from '../model';
import { translate } from '../../../i18n';

export function restoredConversationWasInterrupted(
  messages: ChatMessage[],
  runActive: boolean,
  liveTransport: boolean,
): boolean {
  if (liveTransport) return false;
  const tail = messages[messages.length - 1];
  if (tail && hasDurableAssistantPayload(tail)) return false;
  return runActive || tail?.role === 'user';
}

export function actionOnlyFallback(actions: WorkspaceAction[] | undefined): string {
  const kinds = new Set((actions || []).map((action) => action.kind));
  if (kinds.has('map_recommendation')) return translate('actionMapReady');
  if (kinds.has('meeting_create')) return translate('actionMeetingReady');
  if (kinds.has('calendar_changes')) return translate('actionCalendarReady');
  if (kinds.has('image_generate')) return translate('actionImageReady');
  return '';
}

/**
 * Message rows belong to the conversation that rendered them.
 *
 * React can commit the new conversation id one render before the reducer has
 * replaced the old rows. Persisting that transient combination copies the old
 * conversation into a newly-created one. The switch render is therefore only
 * a hand-off; the following hydrated render may be cached normally.
 */
export function shouldPersistRenderedMessages(
  renderedConversationId: string,
  activeConversationId: string,
): boolean {
  return renderedConversationId === activeConversationId;
}

/**
 * Only the live edge can own an active generation.
 *
 * Older releases could persist an interrupted row with `streaming=true`.
 * Treating any historical row as active permanently disabled every Action and
 * clarification card restored after it. The transport already serializes one
 * turn per conversation, so a streaming row that is not the final row is
 * necessarily stale presentation state.
 */
export function isConversationGenerationActive(messages: ChatMessage[]): boolean {
  let activeIndex = -1;
  messages.forEach((message, index) => {
    if (message.role === 'ai' && message.streaming === true) activeIndex = index;
  });
  if (activeIndex < 0) return false;
  return !messages.slice(activeIndex + 1).some((message) => (
    message.role === 'ai' && !message.streaming
  ));
}
