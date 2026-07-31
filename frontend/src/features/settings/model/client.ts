import { requestJson } from '../../../shared/transport/httpClient';


export const routes = Object.freeze([
  '/auth/session',
  '/provider_usage',
  '/reset',
  '/reset-files',
]);

export function loadSettingsSession<T>(): Promise<T> {
  return requestJson<T>('/auth/session');
}

export function loadProviderUsage<T>(conversationId: string): Promise<T> {
  return requestJson<T>('/provider_usage', {
    headers: { 'makers-conversation-id': conversationId },
  });
}

export function resetSettingsData<T>(
  conversationId: string,
  confirmation: string,
): Promise<T> {
  return requestJson<T>('/reset', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'makers-conversation-id': conversationId,
    },
    body: JSON.stringify({ confirmation }),
  });
}
