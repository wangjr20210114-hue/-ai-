const ACCOUNT_CHOOSER_KEY = 'floris.auth.account-chooser.v1';

function storage(): Storage | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
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
