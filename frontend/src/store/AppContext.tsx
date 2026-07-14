import { useReducer, type ReactNode } from 'react';
import {
  AppDispatchContext,
  AppStateContext,
  initialState,
  reducer,
} from './appState';
import { getOrCreateConversationId, getOrCreateUserId } from '../services/conversation';

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(
    reducer,
    initialState,
    (base) => {
      const userId = getOrCreateUserId();
      return {
        ...base,
        userId,
        sessionId: userId,
        conversationId: getOrCreateConversationId(),
      };
    },
  );
  return (
    <AppStateContext.Provider value={state}>
      <AppDispatchContext.Provider value={dispatch}>
        {children}
      </AppDispatchContext.Provider>
    </AppStateContext.Provider>
  );
}
