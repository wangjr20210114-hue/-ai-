import type { SessionIdentity } from '../../../shared/auth/session';

const RECENT_ACCOUNT_KEY = 'floris.auth.recent-account.v1';

export type RecentAccount = {
  avatarUrl: string;
  displayName: string;
  subjectId: string;
};

export function readRecentAccount(): RecentAccount | null {
  if (typeof window === 'undefined') return null;
  try {
    const parsed = JSON.parse(localStorage.getItem(RECENT_ACCOUNT_KEY) || 'null') as Partial<RecentAccount> | RecentAccount[] | null;
    const value = Array.isArray(parsed) ? parsed[0] : parsed;
    if (!value?.subjectId || !value.displayName) return null;
    return {
      avatarUrl: String(value.avatarUrl || ''),
      displayName: String(value.displayName),
      subjectId: String(value.subjectId),
    };
  } catch {
    return null;
  }
}

export function rememberRecentAccount(identity: SessionIdentity): RecentAccount | null {
  if (typeof window === 'undefined' || identity.auth_type === 'guest') return null;
  const account = {
    avatarUrl: identity.avatar_url || '',
    displayName: identity.display_name || identity.username || identity.id,
    subjectId: identity.subject_id || identity.id,
  };
  try {
    localStorage.setItem(RECENT_ACCOUNT_KEY, JSON.stringify(account));
  } catch {
    // Provider session remains authoritative when local metadata is unavailable.
  }
  return account;
}

export function clearExpiredRecentAccount(): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem(RECENT_ACCOUNT_KEY);
  } catch {
    // Expiry remains authoritative even when local metadata cannot be changed.
  }
}
