import { createContext, useContext } from 'react';
import type { AppSession } from '../../services/auth';

export interface SessionContextValue extends AppSession {
  logout: () => Promise<void>;
}

export const SessionContext = createContext<SessionContextValue | null>(null);
export function useSession() { return useContext(SessionContext); }
