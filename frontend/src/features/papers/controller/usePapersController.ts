import { useCallback, useState } from 'react';

import * as paperApi from '../../../services/paperApi';
import { loadLibrary, readPaper, searchPapers } from '../model/client';


export function usePapersController(conversationId = '') {
  const [data, setData] = useState<unknown>(null);
  const [error, setError] = useState('');
  const run = useCallback(async (operation: () => Promise<unknown>) => {
    setError('');
    try {
      const result = await operation();
      setData(result);
      return result;
    } catch (value) {
      setError(String((value as Error)?.message || value));
      throw value;
    }
  }, []);
  return {
    data,
    error,
    search: (query: string) => run(() => searchPapers(query)),
    read: (input: Record<string, unknown>) => run(
      () => readPaper(conversationId, input),
    ),
    library: () => run(() => loadLibrary()),
    api: paperApi,
  };
}
