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
