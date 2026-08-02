import {
  authorizedFetch,
  currentAuthSession,
  ensureAuthSession,
  logoutSession,
  type AuthSession,
} from '../../../shared/auth/session';

const environmentId = String(import.meta.env.VITE_CLOUDBASE_ENV_ID || '').trim();
const region = String(import.meta.env.VITE_CLOUDBASE_REGION || 'ap-shanghai').trim();
const publishableKey = String(import.meta.env.VITE_CLOUDBASE_PUBLISHABLE_KEY || '').trim();

type CloudBaseResult = {
  data?: unknown;
  error?: { message?: string; error_description?: string } | string | null;
  [key: string]: unknown;
};

type OtpVerifier = {
  verifyOtp: (params: { token: string }) => Promise<CloudBaseResult>;
};

type CloudBaseAuth = {
  signInWithOtp: (params: {
    email: string;
    options?: { shouldCreateUser?: boolean };
  }) => Promise<CloudBaseResult>;
  signInWithOAuth: (params: {
    provider: string;
    options: { redirectTo: string; skipBrowserRedirect?: boolean };
  }) => Promise<CloudBaseResult>;
  getSession: () => Promise<CloudBaseResult>;
  signOut: () => Promise<CloudBaseResult>;
};

export const cloudBaseConfigured = Boolean(
  environmentId && publishableKey && region === 'ap-shanghai',
);

let authClientPromise: Promise<CloudBaseAuth> | null = null;

let otpVerifier: OtpVerifier | null = null;

async function requireClient(): Promise<CloudBaseAuth> {
  if (!cloudBaseConfigured) {
    throw new Error('CloudBase authentication is not configured');
  }
  if (!authClientPromise) {
    authClientPromise = import('@cloudbase/js-sdk').then(({ default: cloudbase }) => (
      cloudbase.init({
        env: environmentId,
        region,
        accessKey: publishableKey,
        timeout: 15_000,
        auth: { detectSessionInUrl: true },
      }).auth() as unknown as CloudBaseAuth
    ));
  }
  return authClientPromise;
}

function resultData(result: CloudBaseResult): Record<string, unknown> {
  return result?.data && typeof result.data === 'object'
    ? result.data as Record<string, unknown>
    : {};
}

function throwResultError(result: CloudBaseResult): void {
  if (!result?.error) return;
  const error = result.error;
  throw new Error(typeof error === 'string'
    ? error
    : error.message || error.error_description || 'CloudBase authentication failed');
}

function accessTokenFrom(result: CloudBaseResult): string {
  const data = resultData(result);
  const session = data.session && typeof data.session === 'object'
    ? data.session as Record<string, unknown>
    : {};
  return String(
    session.access_token
    || session.accessToken
    || data.access_token
    || data.accessToken
    || result.access_token
    || result.accessToken
    || '',
  ).trim();
}

async function currentAccessToken(result?: CloudBaseResult): Promise<string> {
  const immediate = result ? accessTokenFrom(result) : '';
  if (immediate) return immediate;
  const session = await (await requireClient()).getSession();
  throwResultError(session);
  return accessTokenFrom(session);
}

async function exchangeForFlorisSession(accessToken: string): Promise<AuthSession> {
  if (!accessToken) throw new Error('CloudBase did not return an access token');
  const endpoint = currentAuthSession()?.login.cloudbase_session_url
    || '/auth/cloudbase/session';
  const response = await authorizedFetch(endpoint, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ access_token: accessToken }),
  });
  const body = await response.json().catch(() => ({})) as { error?: string };
  if (!response.ok) throw new Error(body.error || 'Floris could not verify this login');
  return ensureAuthSession(true);
}

export async function restoreCloudBaseSession(): Promise<AuthSession | null> {
  if (!cloudBaseConfigured) return null;
  const session = await (await requireClient()).getSession();
  throwResultError(session);
  const accessToken = accessTokenFrom(session);
  return accessToken ? exchangeForFlorisSession(accessToken) : null;
}

/** Inspect the provider-owned local session without exposing or copying its
 * refresh credentials. This powers a real one-click resume when CloudBase can
 * still refresh the last account. */
export async function hasRestorableCloudBaseSession(): Promise<boolean> {
  if (!cloudBaseConfigured) return false;
  const session = await (await requireClient()).getSession();
  throwResultError(session);
  return Boolean(accessTokenFrom(session));
}

export async function sendEmailOtp(email: string): Promise<void> {
  const result = await (await requireClient()).signInWithOtp({
    email,
    options: { shouldCreateUser: true },
  });
  throwResultError(result);
  const data = resultData(result);
  if (typeof data.verifyOtp !== 'function') {
    throw new Error('CloudBase did not return an OTP verifier');
  }
  otpVerifier = data as unknown as OtpVerifier;
}

export async function verifyEmailOtp(code: string): Promise<AuthSession> {
  if (!otpVerifier) throw new Error('Request an email code first');
  const result = await otpVerifier.verifyOtp({ token: code });
  throwResultError(result);
  otpVerifier = null;
  return exchangeForFlorisSession(await currentAccessToken(result));
}

export async function startGithubLogin(): Promise<void> {
  const redirectTo = `${window.location.origin}${window.location.pathname}${window.location.search}`;
  const result = await (await requireClient()).signInWithOAuth({
    provider: 'github',
    options: { redirectTo, skipBrowserRedirect: true },
  });
  throwResultError(result);
  const data = resultData(result);
  const url = String(data.url || data.uri || data.redirectTo || '').trim();
  if (!url) throw new Error('CloudBase did not return a GitHub authorization URL');
  window.location.assign(url);
}

export async function signOutEverywhere(): Promise<AuthSession> {
  if (cloudBaseConfigured) {
    const result = await (await requireClient()).signOut();
    throwResultError(result);
  }
  return logoutSession();
}
