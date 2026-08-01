import type { AuthSession } from '../../../shared/auth/session';

export type ReadingAccess = 'loading' | 'login_required' | 'available' | 'unavailable';

export function readingAccess(session: AuthSession | null | undefined): ReadingAccess {
  if (!session) return 'loading';
  return session.identity.auth_type === 'guest' ? 'login_required' : 'available';
}
