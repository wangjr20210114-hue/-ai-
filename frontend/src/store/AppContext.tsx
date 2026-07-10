import { useReducer, type ReactNode } from 'react';
import {
  AppDispatchContext,
  AppStateContext,
  initialState,
  reducer,
} from './appState';

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  return (
    <AppStateContext.Provider value={state}>
      <AppDispatchContext.Provider value={dispatch}>
        {children}
      </AppDispatchContext.Provider>
    </AppStateContext.Provider>
  );
}
