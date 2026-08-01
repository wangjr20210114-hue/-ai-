import { useCallback, useState } from 'react';

import {
  DataResetError,
  getProviderUsage,
  intelligenceOperation,
  proactiveOperation,
  resetApplicationData,
} from '../model/client';
import { workspaceOperation } from '../../calendar/model/client';
import { searchMakersPlaces } from '../../maps/model/client';
import {
  getReadingSettings,
  updateReadingSettings,
} from '../../../services/paperApi';
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
  const intelligence = useCallback(
    (operation = 'get', input: Record<string, unknown> = {}) => (
      intelligenceOperation(conversationId, operation, input)
    ),
    [conversationId],
  );
  const proactive = useCallback(
    (operation = 'get', input: Record<string, unknown> = {}) => (
      proactiveOperation(conversationId, operation, input)
    ),
    [conversationId],
  );
  const providerUsage = useCallback(
    () => getProviderUsage(conversationId),
    [conversationId],
  );
  const resetApplication = useCallback(
    (confirmation: string) => resetApplicationData(
      conversationId,
      confirmation,
    ),
    [conversationId],
  );
  const workspace = useCallback(
    (operation: string, input: Record<string, unknown> = {}) => (
      workspaceOperation(conversationId, operation, input)
    ),
    [conversationId],
  );
  const searchPlaces = useCallback(
    (query: string, city = '全国') => searchMakersPlaces(
      conversationId,
      query,
      city,
    ),
    [conversationId],
  );
  return {
    session,
    usage,
    error,
    refresh,
    reset: (confirmation: string) => resetSettingsData(
      conversationId,
      confirmation,
    ),
    intelligence,
    proactive,
    providerUsage,
    resetApplication,
    workspace,
    searchPlaces,
    getReadingSettings,
    updateReadingSettings,
    paymentAvailable: false,
  };
}

export { DataResetError };
