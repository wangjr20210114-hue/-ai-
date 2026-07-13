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

const TOKEN_STORAGE_KEY = 'yuanbao.localAccessToken';
let tokenPromise: Promise<string> | null = null;

function readCachedToken(): string {
  try {
    return window.sessionStorage.getItem(TOKEN_STORAGE_KEY) || '';
  } catch {
    return '';
  }
}

function cacheToken(token: string) {
  try {
    window.sessionStorage.setItem(TOKEN_STORAGE_KEY, token);
  } catch {
    // The in-memory promise remains valid for this page lifecycle.
  }
}

export async function getLocalAccessToken(): Promise<string> {
  if (isEdgeOne) return 'edgeone-platform';
  const cached = readCachedToken();
  if (cached) return cached;
  if (!tokenPromise) {
    tokenPromise = fetch('/api/setup/access-token', {
      method: 'GET',
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    })
      .then(async (response) => {
        if (!response.ok) throw new Error('无法获取本地访问令牌');
        const data = (await response.json()) as { token?: string };
        if (!data.token) throw new Error('本地访问令牌响应无效');
        cacheToken(data.token);
        return data.token;
      })
      .catch((error) => {
        tokenPromise = null;
        throw error;
      });
  }
  return tokenPromise;
}

export async function authorizedFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  if (isEdgeOne) {
    const url = typeof input === 'string' ? input : input.toString();
    return fetch(withEdgeOneAuth(url), { ...init, credentials: 'same-origin' });
  }
  const token = await getLocalAccessToken();
  const headers = new Headers(init.headers);
  headers.set('X-Agent-Token', token);
  return fetch(input, { ...init, headers, credentials: init.credentials || 'same-origin' });
}
