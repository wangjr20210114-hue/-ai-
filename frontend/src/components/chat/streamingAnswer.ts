const MEDIA_SLOT_PREFIX = '[[YUANBAO_MEDIA';

/**
 * Preserve complete Markdown for live rendering while hiding only syntax that
 * cannot be rendered yet. Complete media slots stay in the stream so the
 * Markdown renderer can replace them with reviewed images immediately.
 */
export function streamingMarkdownAnswer(content: string): string {
  let visible = content;
  const markerStart = visible.lastIndexOf('[[');
  if (markerStart >= 0) {
    const suffix = visible.slice(markerStart);
    const isMediaMarker = MEDIA_SLOT_PREFIX.startsWith(suffix) || suffix.startsWith(MEDIA_SLOT_PREFIX);
    if (isMediaMarker && !suffix.includes(']]')) visible = visible.slice(0, markerStart);
  }

  // A Markdown image cannot render until its closing parenthesis arrives.
  // Hide that short-lived tail instead of exposing `![alt](partial-url`.
  const imageStart = visible.lastIndexOf('![');
  if (imageStart >= 0) {
    const suffix = visible.slice(imageStart);
    const linkStart = suffix.indexOf('](');
    if (linkStart < 0 || suffix.indexOf(')', linkStart + 2) < 0) {
      visible = visible.slice(0, imageStart);
    }
  }
  return visible;
}
