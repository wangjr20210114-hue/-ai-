const COMPLETE_MEDIA_SLOT = /\[\[YUANBAO_MEDIA(?:\s*:\s*\d+)?\]\]/g;
const MEDIA_SLOT_PREFIX = '[[YUANBAO_MEDIA';

/** Keep the live text node monotonic without exposing internal media markers. */
export function visibleStreamingAnswer(content: string): string {
  const cleaned = content.replace(COMPLETE_MEDIA_SLOT, '');
  const markerStart = cleaned.lastIndexOf('[[');
  if (markerStart < 0) return cleaned;
  const suffix = cleaned.slice(markerStart);
  return MEDIA_SLOT_PREFIX.startsWith(suffix) || suffix.startsWith(MEDIA_SLOT_PREFIX)
    ? cleaned.slice(0, markerStart)
    : cleaned;
}
