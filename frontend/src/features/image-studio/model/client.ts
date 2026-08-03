import { translate } from '../../../i18n';
import { authorizedFetch } from '../../../shared/auth/session';
import { requestRaw } from '../../../shared/transport/httpClient';
import { splitSseFrames } from '../../../shared/transport/sseClient';
import type { WorkspaceAction } from '../../../shared/types';
import { makersConversationHeaders } from '../../../services/conversation';


export const routes = Object.freeze(['/image']);

export function loadGeneratedImage(url: string): Promise<Response> {
  return requestRaw(url);
}

export async function streamImageEdit(
  conversationId: string,
  prompt: string,
  parentActionId: string,
): Promise<WorkspaceAction> {
  const response = await authorizedFetch('/image', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...makersConversationHeaders(conversationId),
    },
    body: JSON.stringify({
      prompt,
      parent_action_id: parentActionId,
    }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({})) as { error?: string };
    throw new Error(
      data.error || translate('imageEditStatusFailed', {
        status: response.status,
      }),
    );
  }
  const reader = response.body?.getReader();
  if (!reader) throw new Error(translate('imageEditProgressReadFailed'));
  const decoder = new TextDecoder();
  let buffer = '';
  let action: WorkspaceAction | undefined;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parsed = splitSseFrames(buffer);
    buffer = parsed.rest;
    for (const frame of parsed.frames) {
      if (frame === '[DONE]') break;
      try {
        const event = JSON.parse(frame) as {
          type?: string;
          action?: WorkspaceAction;
        };
        if (event.type === 'image_action' && event.action) {
          action = event.action;
        }
      } catch {
        // Heartbeats and malformed frames do not end the edit.
      }
    }
  }
  if (!action) throw new Error(translate('imageEditNoVersion'));
  return action;
}
