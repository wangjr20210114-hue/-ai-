const OAUTH_INTENT_KEY = 'floris.auth.oauth-intent.v1';
const ACCOUNT_CHOOSER_KEY = 'floris.auth.account-chooser.v1';
const OAUTH_INTENT_TTL_MS = 15 * 60 * 1000;

function storage(): Storage | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function markOAuthLoginIntent(now = Date.now()): void {
  storage()?.setItem(OAUTH_INTENT_KEY, String(now));
}

export function consumeOAuthLoginIntent(now = Date.now()): boolean {
  const target = storage();
  if (!target) return false;
  const createdAt = Number(target.getItem(OAUTH_INTENT_KEY) || 0);
  target.removeItem(OAUTH_INTENT_KEY);
  return createdAt > 0 && now - createdAt >= 0 && now - createdAt <= OAUTH_INTENT_TTL_MS;
}

export function requestAccountChooserAfterReload(): void {
  storage()?.setItem(ACCOUNT_CHOOSER_KEY, '1');
}

export function consumeAccountChooserRequest(): boolean {
  const target = storage();
  if (!target) return false;
  const requested = target.getItem(ACCOUNT_CHOOSER_KEY) === '1';
  target.removeItem(ACCOUNT_CHOOSER_KEY);
  return requested;
}
