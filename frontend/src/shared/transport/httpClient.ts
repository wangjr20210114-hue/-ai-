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

export function requestRaw(
  input: RequestInfo | URL,
  init: RequestInit = {},
  withSignedSession = true,
): Promise<Response> {
  if (withSignedSession) return authorizedFetch(input, init);
  return fetch(input, init);
}

/**
 * Upload a Blob to a backend-issued URL while reporting transfer progress.
 * Feature code stays transport-agnostic and never opens its own network path.
 */
export function uploadRawWithProgress(
  input: string,
  body: Blob,
  contentType: string,
  onProgress: (percent: number) => void,
): Promise<Response> {
  if (typeof XMLHttpRequest === 'undefined') {
    return fetch(input, {
      method: 'PUT',
      headers: { 'Content-Type': contentType },
      body,
    });
  }
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open('PUT', input, true);
    request.setRequestHeader('Content-Type', contentType);
    request.upload.onprogress = (event) => {
      if (!event.lengthComputable || event.total <= 0) return;
      onProgress(Math.min(100, Math.max(0, Math.round((event.loaded / event.total) * 100))));
    };
    request.onload = () => resolve(new Response(null, {
      status: request.status,
      statusText: request.statusText,
    }));
    request.onerror = () => reject(new TypeError());
    request.onabort = () => reject(Object.assign(new Error(), { name: 'AbortError' }));
    request.send(body);
  });
}
