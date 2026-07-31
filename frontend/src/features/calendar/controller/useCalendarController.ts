import { useCallback, useState } from 'react';

import {
  calendarOperation,
} from '../model/client';
import type { CalendarWorkspaceResponse } from '../model/types';


export function useCalendarController(conversationId: string) {
  const [state, setState] = useState<CalendarWorkspaceResponse | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const execute = useCallback(async (
    operation: string,
    input: Record<string, unknown> = {},
  ) => {
    setLoading(true);
    setError('');
    try {
      const next = await calendarOperation(conversationId, operation, input);
      setState(next);
      return next;
    } catch (value) {
      setError(String((value as Error)?.message || value));
      throw value;
    } finally {
      setLoading(false);
    }
  }, [conversationId]);
  return {
    state,
    loading,
    error,
    propose: (input: Record<string, unknown>) => execute('prepare_calendar', input),
    confirm: (input: Record<string, unknown>) => execute('confirm', input),
    retry: () => execute('get'),
  };
}
