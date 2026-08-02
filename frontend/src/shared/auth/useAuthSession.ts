import { useEffect, useState } from 'react';

import {
  currentAuthSession,
  ensureAuthSession,
  type AuthSession,
} from './session';

export function useAuthSession(): AuthSession | null {
  const [session, setSession] = useState<AuthSession | null>(currentAuthSession());

  useEffect(() => {
    void ensureAuthSession().then(setSession).catch(() => undefined);
    const changed = (event: Event) => {
      setSession((event as CustomEvent<AuthSession>).detail);
    };
    window.addEventListener('floris:auth-changed', changed);
    return () => window.removeEventListener('floris:auth-changed', changed);
  }, []);

  return session;
}
