import type { ChatMessage } from '../../model';

export interface MessageContentRenderer {
  id: string;
  canRender(message: ChatMessage): boolean;
}

function descriptor(
  id: string,
  canRender: (message: ChatMessage) => boolean,
): MessageContentRenderer {
  return Object.freeze({
    id,
    canRender,
  });
}

export const messageContentRenderers: readonly MessageContentRenderer[] = Object.freeze([
  descriptor('search-evidence', (message) => Boolean(message.searchResults)),
  descriptor('paper', (message) => Boolean(message.papers?.length || message.paperFileId)),
  descriptor('action', (message) => Boolean(message.workspaceActions?.length)),
  descriptor('text', () => true),
]);

export function selectRenderer(message: ChatMessage): MessageContentRenderer {
  return messageContentRenderers.find((renderer) => renderer.canRender(message))
    || messageContentRenderers[messageContentRenderers.length - 1];
}
