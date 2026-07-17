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

export interface AppSession {
  mode: 'single_user' | 'multi_user';
  user: { id: string; username: string; roles: string[] };
}

async function authRequest(operation: string, body?: { username: string; password: string }): Promise<AppSession> {
  const response = await fetch(withEdgeOneAuth(`/auth/${encodeURIComponent(operation)}`), {
    method: body ? 'POST' : 'GET',
    credentials: 'same-origin',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => ({})) as AppSession & { error?: string };
  if (!response.ok) throw new Error(data.error || (response.status === 401 ? '请登录后继续' : '身份服务不可用'));
  return data;
}

export const getAppSession = () => authRequest('user');
export const loginAppSession = (username: string, password: string) => authRequest('login', { username, password });
export const registerAppSession = (username: string, password: string) => authRequest('register', { username, password });

export async function logoutAppSession(): Promise<void> {
  await fetch(withEdgeOneAuth('/auth/logout'), { method: 'POST', credentials: 'same-origin' });
}

export async function rotateConnectorSecret(): Promise<string> {
  const response = await fetch(withEdgeOneAuth('/auth/connector?operation=rotate'), { method: 'POST', credentials: 'same-origin' });
  const data = await response.json().catch(() => ({})) as { connector_secret?: string; error?: string };
  if (!response.ok || !data.connector_secret) throw new Error(data.error || '无法生成连接器密钥');
  return data.connector_secret;
}

export async function revokeConnectorSecret(): Promise<void> {
  const response = await fetch(withEdgeOneAuth('/auth/connector?operation=revoke'), { method: 'POST', credentials: 'same-origin' });
  if (!response.ok) {
    const data = await response.json().catch(() => ({})) as { error?: string };
    throw new Error(data.error || '无法撤销连接器密钥');
  }
}
