import { requestJson } from '../../../shared/transport/httpClient';
import type { CalendarWorkspaceResponse } from './types';


export const routes = Object.freeze(['/workspace']);

export function calendarOperation(
  conversationId: string,
  operation: string,
  input: Record<string, unknown> = {},
): Promise<CalendarWorkspaceResponse> {
  return requestJson<CalendarWorkspaceResponse>('/workspace', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'makers-conversation-id': conversationId,
    },
    body: JSON.stringify({ operation, ...input }),
  });
}

export async function workspaceOperation(
  conversationId: string,
  operation: string,
  input: Record<string, unknown> = {},
): Promise<CalendarWorkspaceResponse> {
  const data = await calendarOperation(conversationId, operation, input);
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('yuanbao:proactive-refresh', {
      detail: { operation, response: data },
    }));
    if (Array.isArray(data.schedules)) {
      window.dispatchEvent(new CustomEvent('yuanbao:workspace-changed', {
        detail: data,
      }));
      if (Array.isArray(data.changed) && data.changed.length > 0) {
        window.dispatchEvent(new CustomEvent('yuanbao:calendar-changed', {
          detail: data,
        }));
      }
    }
  }
  return data;
}
