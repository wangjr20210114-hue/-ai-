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
    // In-memory promise still keeps the token for this page lifecycle.
  }
}

export async function getLocalAccessToken(): Promise<string> {
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
  const token = await getLocalAccessToken();
  const headers = new Headers(init.headers);
  headers.set('X-Agent-Token', token);
  return fetch(input, { ...init, headers, credentials: init.credentials || 'same-origin' });
}
