const TOKEN_STORAGE_KEY = 'yuanbao.localAccessToken';
let tokenPromise: Promise<string> | null = null;

/** Running on EdgeOne preview/production? */
export const isEdgeOne = typeof window !== 'undefined' && window.location.host.includes('edgeone');

/** Append eo_token/eo_time params for EdgeOne API auth. */
function withEdgeOneAuth(url: string): string {
  if (!isEdgeOne) return url;
  const p = new URLSearchParams(window.location.search);
  const token = p.get('eo_token');
  const time = p.get('eo_time');
  if (!token || !time) return url;
  const sep = url.includes('?') ? '&' : '?';
  return `${url}${sep}eo_token=${token}&eo_time=${time}`;
}

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
    // keep in promise for this page lifecycle
  }
}

export async function getLocalAccessToken(): Promise<string> {
  // On EdgeOne, no local token needed — platform handles auth
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
  // On EdgeOne, skip local token, add eo_token to URL, use cookie auth
  if (isEdgeOne) {
    const url = typeof input === 'string' ? input : input.toString();
    return fetch(withEdgeOneAuth(url), {
      ...init,
      credentials: 'same-origin',
    });
  }
  const token = await getLocalAccessToken();
  const headers = new Headers(init.headers);
  headers.set('X-Agent-Token', token);
  return fetch(input, { ...init, headers, credentials: init.credentials || 'same-origin' });
}
