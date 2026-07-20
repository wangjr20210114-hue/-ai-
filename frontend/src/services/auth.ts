const runtimeMode = import.meta.env.VITE_APP_RUNTIME;

function hasEdgeOneAccessParams(): boolean {
  if (typeof window === 'undefined') return false;
  const params = new URLSearchParams(window.location.search);
  return Boolean(params.get('eo_token') && params.get('eo_time'));
}

function hasEdgeOneHost(): boolean {
  if (typeof window === 'undefined') return false;
  const host = window.location.hostname;
  return host.endsWith('.edgeone.cool') || host.endsWith('.edgeone.site');
}

/** Build mode is authoritative; host/query detection keeps preview URLs compatible. */
export const isEdgeOne = runtimeMode === 'edgeone'
  || hasEdgeOneHost()
  || hasEdgeOneAccessParams();

/** Preserve preview access parameters on Makers agent/function calls. */
export function withEdgeOneAuth(url: string): string {
  if (!isEdgeOne || typeof window === 'undefined') return url;
  const source = new URLSearchParams(window.location.search);
  const token = source.get('eo_token');
  const time = source.get('eo_time');
  if (!token || !time) return url;

  const [withoutHash, hash = ''] = url.split('#', 2);
  const separator = withoutHash.includes('?') ? '&' : '?';
  const auth = new URLSearchParams({ eo_token: token, eo_time: time }).toString();
  return `${withoutHash}${separator}${auth}${hash ? `#${hash}` : ''}`;
}

export async function authorizedFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  const url = typeof input === 'string' ? input : input.toString();
  return fetch(withEdgeOneAuth(url), { ...init, credentials: 'same-origin' });
}
