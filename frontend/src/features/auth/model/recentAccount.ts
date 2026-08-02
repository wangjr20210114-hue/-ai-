import type { SessionIdentity } from '../../../shared/auth/session';

const RECENT_ACCOUNT_KEY = 'floris.auth.recent-account.v1';
const MAX_RECENT_ACCOUNTS = 8;

export type RecentAccount = {
  avatarUrl: string;
  displayName: string;
  email: string;
  lastUsedAt: number;
  subjectId: string;
};

export function readRecentAccounts(): RecentAccount[] {
  if (typeof window === 'undefined') return [];
  try {
    const parsed = JSON.parse(localStorage.getItem(RECENT_ACCOUNT_KEY) || '[]') as unknown;
    const values = Array.isArray(parsed) ? parsed : [parsed];
    return values
      .filter((value): value is Partial<RecentAccount> => Boolean(value && typeof value === 'object'))
      .filter((value) => Boolean(value.subjectId && value.displayName))
      .map((value) => ({
        avatarUrl: String(value.avatarUrl || ''),
        displayName: String(value.displayName),
        email: String(value.email || ''),
        lastUsedAt: Number(value.lastUsedAt || 0),
        subjectId: String(value.subjectId),
      }))
      .sort((a, b) => b.lastUsedAt - a.lastUsedAt)
      .slice(0, MAX_RECENT_ACCOUNTS);
  } catch {
    return [];
  }
}

export function readRecentAccount(): RecentAccount | null {
  return readRecentAccounts()[0] || null;
}

export function rememberRecentAccount(identity: SessionIdentity): RecentAccount | null {
  if (typeof window === 'undefined' || identity.auth_type === 'guest') return null;
  const account = {
    avatarUrl: identity.avatar_url || '',
    displayName: identity.display_name || identity.username || identity.id,
    email: identity.username || '',
    lastUsedAt: Date.now(),
    subjectId: identity.subject_id || identity.id,
  };
  try {
    const accounts = [
      account,
      ...readRecentAccounts().filter((item) => item.subjectId !== account.subjectId),
    ].slice(0, MAX_RECENT_ACCOUNTS);
    localStorage.setItem(RECENT_ACCOUNT_KEY, JSON.stringify(accounts));
  } catch {
    // Provider session remains authoritative when local metadata is unavailable.
  }
  return account;
}
