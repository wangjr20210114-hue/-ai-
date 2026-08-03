const INTERNAL_ACTION_BUTTON = /<button\b[^>]*\bdata-action(?:-id)?\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)[^>]*>[\s\S]*?<\/button\s*>/gi;

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
 * Structured workspace actions are rendered by MessageBubble, never by model
 * authored HTML. Hide leaked legacy action markup without stripping ordinary
 * HTML examples that a user may legitimately ask the assistant to discuss.
 */
export function publicAssistantMarkdown(content: string): string {
  let visible = String(content || '').replace(INTERNAL_ACTION_BUTTON, '');
  const openButton = visible.toLowerCase().lastIndexOf('<button');
  if (openButton >= 0) {
    const suffix = visible.slice(openButton);
    if (
      /\bdata-action(?:-id)?\s*=/i.test(suffix)
      && !/<\/button\s*>/i.test(suffix)
    ) {
      visible = visible.slice(0, openButton);
    }
  }
  return visible.replace(/\n{3,}/g, '\n\n').trimEnd();
}

/**
 * Preserve complete Markdown for live rendering while hiding only syntax that
 * cannot be rendered yet. Legacy media text is not a streaming protocol; the
 * Markdown renderer sanitizes it without using it to choose an image position.
 */
export function streamingMarkdownAnswer(content: string): string {
  let visible = content;

  // Internal provider/citation markers are never part of the public rich-
  // search protocol. Completed legacy markers are sanitized by the Markdown
  // renderer; hold an unfinished `[[...` tail so it cannot flash on screen.
  const internalMarkerStart = visible.lastIndexOf('[[');
  if (internalMarkerStart >= 0) {
    const suffix = visible.slice(internalMarkerStart + 2);
    if (!suffix.includes(']]')) visible = visible.slice(0, internalMarkerStart);
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
