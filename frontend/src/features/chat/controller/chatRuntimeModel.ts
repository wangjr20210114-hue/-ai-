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
