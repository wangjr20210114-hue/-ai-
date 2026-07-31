import { requestJson } from '../../../shared/transport/httpClient';


export const routes = Object.freeze(['/places', '/routes']);

export function searchPlaces<T>(
  conversationId: string,
  input: Record<string, unknown>,
): Promise<T> {
  return requestJson<T>('/places', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'makers-conversation-id': conversationId,
    },
    body: JSON.stringify(input),
  });
}

export function planRoute<T>(
  conversationId: string,
  input: Record<string, unknown>,
): Promise<T> {
  return requestJson<T>('/routes', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'makers-conversation-id': conversationId,
    },
    body: JSON.stringify(input),
  });
}
