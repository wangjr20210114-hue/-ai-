import { requestJson } from '../../../shared/transport/httpClient';


export const routes = Object.freeze(['/papers', '/reader', '/library']);

export function searchPapers<T>(query: string): Promise<T> {
  return requestJson<T>(`/papers?topic=${encodeURIComponent(query)}`);
}

export function readPaper<T>(
  conversationId: string,
  input: Record<string, unknown>,
): Promise<T> {
  return requestJson<T>('/reader', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'makers-conversation-id': conversationId,
    },
    body: JSON.stringify(input),
  });
}

export function loadLibrary<T>(): Promise<T> {
  return requestJson<T>('/library');
}
