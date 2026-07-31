import { authorizedFetch } from '../auth/session';


export class HttpClientError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.name = 'HttpClientError';
    this.status = status;
    this.body = body;
  }
}

export async function requestJson<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await authorizedFetch(path, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init.headers || {}),
    },
  });
  const body = await response.json().catch(() => null) as T | { error?: string } | null;
  if (!response.ok) {
    const message = body && typeof body === 'object' && 'error' in body
      ? String(body.error || `Request failed (${response.status})`)
      : `Request failed (${response.status})`;
    throw new HttpClientError(response.status, message, body);
  }
  return body as T;
}
