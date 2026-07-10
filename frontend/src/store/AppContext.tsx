import {
  createContext,
  useContext,
  useReducer,
  type Dispatch,
  type ReactNode,
} from 'react';
import type {
  ChatMessage,
  ThemeMode,
  TravelPlan,
  ScheduleItem,
} from '../types';

const THEME_KEY = 'travel-theme';

function initialTheme(): ThemeMode {
  const saved = (typeof localStorage !== 'undefined' && localStorage.getItem(THEME_KEY)) as ThemeMode | null;
  return saved === 'dark' || saved === 'light' ? saved : 'light';
}

interface AppState {
  sessionId: string;
  connected: boolean;
  theme: ThemeMode;
  thinking: boolean;
  draft: string;
  messages: ChatMessage[];
  plans: TravelPlan[];
  schedules: ScheduleItem[];
  travelContext: {
    collected: Record<string, any>;
    missing: string[];
    reasoning: string;
    context: Record<string, any>;
  } | null;
  scheduleViewDate: Date | null;
}

type Action =
  | { type: 'SET_CONNECTED'; payload: boolean }
  | { type: 'SET_THEME'; payload: ThemeMode }
  | { type: 'SET_THINKING'; payload: boolean }
  | { type: 'SET_DRAFT'; payload: string }
  | { type: 'ADD_MESSAGE'; payload: ChatMessage }
  | { type: 'UPDATE_MESSAGE'; payload: { id: string; patch: Partial<ChatMessage>; delta?: string } }
  | { type: 'SET_PLANS'; payload: TravelPlan[] }
  | { type: 'ADD_PLAN'; payload: TravelPlan }
  | { type: 'UPDATE_PLAN'; payload: TravelPlan }
  | { type: 'DELETE_PLAN'; payload: string }
  | { type: 'SET_SCHEDULES'; payload: ScheduleItem[] }
  | { type: 'ADD_SCHEDULE'; payload: ScheduleItem }
  | { type: 'UPDATE_SCHEDULE'; payload: ScheduleItem }
  | { type: 'DELETE_SCHEDULE'; payload: string }
  | { type: 'SET_TRAVEL_CONTEXT'; payload: any }
  | { type: 'SHOW_SCHEDULE_VIEW'; payload: Date | null }
  | { type: 'CLEAR_ALL_STREAMING'; payload: {} };

const initialState: AppState = {
  sessionId: 'sess-' + Math.random().toString(36).slice(2, 10),
  connected: false,
  theme: initialTheme(),
  thinking: false,
  draft: '',
  messages: [],
  plans: [],
  schedules: [],
  travelContext: null,
  scheduleViewDate: null,
};

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'SET_CONNECTED':
      return { ...state, connected: action.payload };
    case 'SET_THEME':
      return { ...state, theme: action.payload };
    case 'SET_THINKING':
      return { ...state, thinking: action.payload };
    case 'SET_DRAFT':
      return { ...state, draft: action.payload };
    case 'ADD_MESSAGE':
      return { ...state, messages: [...state.messages, action.payload] };
    case 'UPDATE_MESSAGE':
      return {
        ...state,
        messages: state.messages.map((m) => {
          if (m.id !== action.payload.id) return m;
          if (action.payload.delta !== undefined) {
            // 流式追加
            return { ...m, ...action.payload.patch, content: m.content + action.payload.delta };
          }
          return { ...m, ...action.payload.patch };
        }),
      };
    case 'SET_PLANS':
      return { ...state, plans: action.payload };
    case 'ADD_PLAN':
      return { ...state, plans: [action.payload, ...state.plans] };
    case 'UPDATE_PLAN':
      return {
        ...state,
        plans: state.plans.map((p) => (p.id === action.payload.id ? action.payload : p)),
      };
    case 'DELETE_PLAN':
      return { ...state, plans: state.plans.filter((p) => p.id !== action.payload) };
    case 'SET_SCHEDULES':
      return { ...state, schedules: action.payload };
    case 'ADD_SCHEDULE':
      return { ...state, schedules: [action.payload, ...state.schedules] };
    case 'UPDATE_SCHEDULE':
      return {
        ...state,
        schedules: state.schedules.map((s) => (s.id === action.payload.id ? action.payload : s)),
      };
    case 'DELETE_SCHEDULE':
      return { ...state, schedules: state.schedules.filter((s) => s.id !== action.payload) };
    case 'SET_TRAVEL_CONTEXT':
      return { ...state, travelContext: action.payload };
    case 'SHOW_SCHEDULE_VIEW':
      return { ...state, scheduleViewDate: action.payload };
    case 'CLEAR_ALL_STREAMING':
      return {
        ...state,
        messages: state.messages.map((m) =>
          m.streaming ? { ...m, streaming: false } : m
        ),
      };
    default:
      return state;
  }
}

const AppStateContext = createContext<AppState | null>(null);
const AppDispatchContext = createContext<Dispatch<Action> | null>(null);

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

export function useAppState(): AppState {
  const ctx = useContext(AppStateContext);
  if (!ctx) throw new Error('useAppState must be used within AppProvider');
  return ctx;
}

export function useAppDispatch(): Dispatch<Action> {
  const ctx = useContext(AppDispatchContext);
  if (!ctx) throw new Error('useAppDispatch must be used within AppProvider');
  return ctx;
}
