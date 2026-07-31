import { useCallback, useState } from 'react';

import {
  loadProviderUsage,
  loadSettingsSession,
  resetSettingsData,
} from '../model/client';


export function useSettingsController(conversationId: string) {
  const [session, setSession] = useState<unknown>(null);
  const [usage, setUsage] = useState<unknown>(null);
  const [error, setError] = useState('');
  const refresh = useCallback(async () => {
    setError('');
    try {
      const [nextSession, nextUsage] = await Promise.all([
        loadSettingsSession(),
        loadProviderUsage(conversationId),
      ]);
      setSession(nextSession);
      setUsage(nextUsage);
    } catch (value) {
      setError(String((value as Error)?.message || value));
    }
  }, [conversationId]);
  return {
    session,
    usage,
    error,
    refresh,
    reset: (confirmation: string) => resetSettingsData(
      conversationId,
      confirmation,
    ),
    paymentAvailable: false,
  };
}
