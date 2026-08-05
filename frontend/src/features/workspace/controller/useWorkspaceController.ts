import { useCallback } from 'react';

import { workspaceOperation } from '../../calendar/model/client';
import { searchMakersPlaces } from '../../maps/model/client';
import { intelligenceOperation } from '../../settings/model/client';

/** Coordinates the right-hand workspace without making Settings own it. */
export function useWorkspaceController(conversationId: string) {
  const intelligence = useCallback(
    (operation = 'get', input: Record<string, unknown> = {}) => (
      intelligenceOperation(conversationId, operation, input)
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
  return { intelligence, workspace, searchPlaces };
}
