import { useEffect, useReducer, type ReactNode } from 'react';
import {
  AppDispatchContext,
  AppStateContext,
  initialState,
  reducer,
} from './appState';
import { getOrCreateConversationId, loadLocalConversations, saveLocalConversations } from '../services/conversation';

export function AppProvider({ children, userId = 'local-user' }: { children: ReactNode; userId?: string }) {
  const [state, dispatch] = useReducer(
    reducer,
    initialState,
    (base) => ({ ...base, userId, sessionId: userId, conversationId: getOrCreateConversationId(), conversations: loadLocalConversations() }),
  );
  useEffect(() => { saveLocalConversations(state.conversations); }, [state.conversations]);
  return (
    <AppStateContext.Provider value={state}>
      <AppDispatchContext.Provider value={dispatch}>
        {children}
      </AppDispatchContext.Provider>
    </AppStateContext.Provider>
  );
}
