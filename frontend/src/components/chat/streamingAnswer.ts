const MEDIA_SLOT_PREFIX = '[[YUANBAO_MEDIA';

function hideUnclosedDelimiterTail(content: string, delimiter: string): string {
  let count = 0;
  let cursor = 0;
  let last = -1;
  while (cursor < content.length) {
    const next = content.indexOf(delimiter, cursor);
    if (next < 0) break;
    count += 1;
    last = next;
    cursor = next + delimiter.length;
  }
  return count % 2 === 1 && last >= 0 ? content.slice(0, last) : content;
}

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

  // Strong/strike delimiters are rendered only after the matching closing
  // marker arrives. This prevents a brief `**partial phrase` flash while the
  // model is still emitting the emphasized span.
  for (const delimiter of ['**', '__', '~~']) {
    visible = hideUnclosedDelimiterTail(visible, delimiter);
  }
  return visible;
}
