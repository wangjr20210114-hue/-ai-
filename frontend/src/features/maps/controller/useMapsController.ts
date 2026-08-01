import { useCallback, useState } from 'react';

import type {
  MakersMapPlace,
  MakersRouteMode,
  MakersRouteStrategy,
} from '../../../shared/types';
import { workspaceOperation } from '../../calendar/model/client';
import { proactiveOperation } from '../../settings/model/client';
import {
  planMakersRoute,
  planRoute,
  searchMakersPlaces,
  searchPlaces,
} from '../model/client';


export function useMapsController(conversationId: string) {
  const [places, setPlaces] = useState<unknown[]>([]);
  const [route, setRoute] = useState<unknown>(null);
  const [error, setError] = useState('');
  const search = useCallback(async (input: Record<string, unknown>) => {
    setError('');
    try {
      const result = await searchPlaces<{ places?: unknown[] }>(conversationId, input);
      setPlaces(result.places || []);
      return result;
    } catch (value) {
      setError(String((value as Error)?.message || value));
      throw value;
    }
  }, [conversationId]);
  const plan = useCallback(async (input: Record<string, unknown>) => {
    setError('');
    try {
      const result = await planRoute(conversationId, input);
      setRoute(result);
      return result;
    } catch (value) {
      setError(String((value as Error)?.message || value));
      throw value;
    }
  }, [conversationId]);
  const searchVerifiedPlaces = useCallback(
    (query: string, city = '全国') => searchMakersPlaces(
      conversationId,
      query,
      city,
    ),
    [conversationId],
  );
  const planVerifiedRoute = useCallback(
    (
      verifiedPlaces: MakersMapPlace[],
      mode?: MakersRouteMode,
      strategy?: MakersRouteStrategy,
    ) => planMakersRoute(conversationId, verifiedPlaces, mode, strategy),
    [conversationId],
  );
  const updateWorkspace = useCallback(
    (operation: string, input: Record<string, unknown> = {}) => (
      workspaceOperation(conversationId, operation, input)
    ),
    [conversationId],
  );
  const ingestSignal = useCallback(
    (input: Record<string, unknown>) => proactiveOperation(
      conversationId,
      'ingest_signal',
      input,
    ),
    [conversationId],
  );
  return {
    places,
    route,
    error,
    search,
    plan,
    searchVerifiedPlaces,
    planVerifiedRoute,
    updateWorkspace,
    ingestSignal,
  };
}
