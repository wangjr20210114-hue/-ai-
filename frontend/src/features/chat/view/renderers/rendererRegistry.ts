import type { ChatMessage } from '../../../../shared/types';

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
  descriptor('calendar', (message) => Boolean(message.parsedSchedules?.length)),
  descriptor('map', (message) => Boolean(message.travelPlanData)),
  descriptor('action', (message) => Boolean(message.workspaceActions?.length)),
  descriptor('text', () => true),
]);

export function selectRenderer(message: ChatMessage): MessageContentRenderer {
  return messageContentRenderers.find((renderer) => renderer.canRender(message))
    || messageContentRenderers[messageContentRenderers.length - 1];
}
