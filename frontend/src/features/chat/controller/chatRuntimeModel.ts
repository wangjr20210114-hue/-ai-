import { hasDurableAssistantPayload } from '../../../services/conversation';
import type { ChatMessage, SearchMeta, WorkspaceAction } from '../model';
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

export function resolveSearchStartAt(
  current: number | undefined,
  remembered: number | undefined,
  shouldStart: boolean,
  now = Date.now(),
): number | undefined {
  const known = Number(remembered || current || 0);
  return known || (shouldStart ? now : undefined);
}

export function mergeSearchMeta(previous: SearchMeta | undefined, incoming: Partial<SearchMeta>): SearchMeta {
  const previousMedia = previous?.media || [];
  const incomingMedia = Array.isArray(incoming.media) ? incoming.media : [];
  const previousImages = previous?.images || [];
  const incomingImages = Array.isArray(incoming.images) ? incoming.images : [];
  const retainedMedia = incomingMedia.length ? incomingMedia : previousMedia;
  const retainedImages = incomingImages.length ? incomingImages : previousImages;
  return {
    ...(previous || {}),
    ...incoming,
    query: String(incoming.query ?? previous?.query ?? ''),
    results: Array.isArray(incoming.results) ? incoming.results : (previous?.results || []),
    media: retainedMedia,
    images: retainedImages,
    sources_used: Array.isArray(incoming.sources_used) ? incoming.sources_used : (previous?.sources_used || []),
    total: typeof incoming.total === 'number' ? incoming.total : (previous?.total || 0),
    timings_ms: incoming.timings_ms ?? previous?.timings_ms,
    media_pending: previous?.media_pending === false && previousMedia.length > 0
      ? false
      : (incoming.media_pending ?? previous?.media_pending),
  };
}

export function actionOnlyFallback(actions: WorkspaceAction[] | undefined): string {
  const kinds = new Set((actions || []).map((action) => action.kind));
  if (kinds.has('map_recommendation')) return translate('actionMapReady');
  if (kinds.has('meeting_create')) return translate('actionMeetingReady');
  if (kinds.has('calendar_changes')) return translate('actionCalendarReady');
  if (kinds.has('image_generate')) return translate('actionImageReady');
  return '';
}
