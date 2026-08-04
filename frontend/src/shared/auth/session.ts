import { translate } from '../../i18n';

const runtimeMode = import.meta.env.VITE_APP_RUNTIME;

export interface SessionIdentity {
  id: string;
  subject_id: string;
  tenant_id: string;
  username: string;
  display_name: string;
  avatar_url: string;
  auth_type: 'guest' | 'wechat' | 'cloudbase';
  auth_providers: string[];
  membership: 'guest' | 'free' | 'plus' | 'pro';
  roles: string[];
}

export interface AuthSession {
  identity: SessionIdentity;
  entitlements: {
    plan: SessionIdentity['membership'];
    limits: {
      searchDepth?: string;
      search_depth?: string;
      concurrentRuns?: number;
      concurrent_runs?: number;
      dailyTokens?: number;
      daily_tokens?: number;
      userSkillUploads?: number;
      user_skill_uploads?: number;
    };
    payment_available: boolean;
  };
  login: {
    cloudbase_available: boolean;
    cloudbase_session_url: string;
    wechat_available: boolean;
    wechat_mode: 'qr' | 'in_app';
    wechat_start_url: string;
    logout_url: string;
  };
}

let authSessionPromise: Promise<AuthSession> | null = null;
let cachedAuthSession: AuthSession | null = null;
// Ignore a late guest bootstrap response after a login/logout refresh.
let authSessionGeneration = 0;
const LOCAL_IDENTITY_KEY = 'floris.auth.identity';

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

export function wechatLoginLabelKey(
  session: AuthSession | null,
): 'wechatInAppLogin' | 'wechatQrLogin' {
  return session?.login.wechat_mode === 'in_app'
    ? 'wechatInAppLogin'
    : 'wechatQrLogin';
}

export function wechatLoginUnavailableKey(
  session: AuthSession | null,
): 'wechatInAppLoginUnavailable' | 'wechatQrLoginUnavailable' {
  return session?.login.wechat_mode === 'in_app'
    ? 'wechatInAppLoginUnavailable'
    : 'wechatQrLoginUnavailable';
}

export const withSession = withEdgeOneAuth;

export function currentAuthSession(): AuthSession | null {
  return cachedAuthSession;
}

export const OPEN_AUTH_DIALOG_EVENT = 'floris:open-auth';

export function openAuthDialog(): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(OPEN_AUTH_DIALOG_EVENT));
}

export async function ensureAuthSession(force = false): Promise<AuthSession> {
  if (force) {
    authSessionPromise = null;
    authSessionGeneration += 1;
  }
  if (authSessionPromise) return authSessionPromise;
  const generation = authSessionGeneration;
  authSessionPromise = fetch(withEdgeOneAuth('/auth/session'), {
    method: 'GET',
    credentials: 'same-origin',
    headers: { Accept: 'application/json' },
  }).then(async (response) => {
    const data = await response.json().catch(() => ({})) as Partial<AuthSession> & { error?: string };
    if (!response.ok || !data.identity || !data.entitlements || !data.login) {
      throw new Error(data.error || translate('secureSessionFailed'));
    }
    if (generation !== authSessionGeneration) {
      throw new Error(translate('staleAuthSession'));
    }
    cachedAuthSession = data as AuthSession;
    if (typeof window !== 'undefined') {
      try {
        const previousIdentity = localStorage.getItem(LOCAL_IDENTITY_KEY);
        localStorage.setItem(LOCAL_IDENTITY_KEY, cachedAuthSession.identity.id);
        if (previousIdentity && previousIdentity !== cachedAuthSession.identity.id) {
          localStorage.removeItem('yuanbao.v6.conversationId');
          localStorage.removeItem('yuanbao.v6.conversations');
          sessionStorage.clear();
          window.location.reload();
        }
      } catch {
        // Server-side tenant scoping remains authoritative when storage is unavailable.
      }
      window.dispatchEvent(new CustomEvent('floris:auth-changed', {
        detail: cachedAuthSession,
      }));
    }
    return cachedAuthSession;
  }).catch((error) => {
    if (generation === authSessionGeneration) authSessionPromise = null;
    throw error;
  });
  return authSessionPromise;
}

export function startWechatLogin(returnTo = window.location.pathname): void {
  const session = currentAuthSession();
  const start = session?.login.wechat_start_url || '/auth/wechat/start';
  const url = new URL(withEdgeOneAuth(start), window.location.origin);
  url.searchParams.set('return_to', returnTo.startsWith('/') ? returnTo : '/chatBot');
  window.location.assign(url.toString());
}

export async function logoutSession(): Promise<AuthSession> {
  const endpoint = currentAuthSession()?.login.logout_url || '/auth/logout';
  await fetch(withEdgeOneAuth(endpoint), {
    method: 'POST',
    credentials: 'same-origin',
  });
  cachedAuthSession = null;
  authSessionPromise = null;
  authSessionGeneration += 1;
  return ensureAuthSession(true);
}

export async function authorizedFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  const url = typeof input === 'string' ? input : input.toString();
  if (!url.startsWith('/auth/')) await ensureAuthSession();
  return fetch(withEdgeOneAuth(url), { ...init, credentials: 'same-origin' });
}
