import { useCallback, useState } from 'react';

import { planRoute, searchPlaces } from '../model/client';


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
  return { places, route, error, search, plan };
}
