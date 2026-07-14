import { createContext, useContext, type Dispatch } from 'react';
import type {
  ChatMessage,
  ThemeMode,
  ScheduleItem,
  MakersMapPlace,
} from '../types';

const THEME_KEY = 'travel-theme';

function initialTheme(): ThemeMode {
  const saved = (typeof localStorage !== 'undefined' && localStorage.getItem(THEME_KEY)) as ThemeMode | null;
  return saved === 'dark' || saved === 'light' ? saved : 'light';
}

export interface AppState {
  userId: string;
  conversationId: string;
  sessionId: string;
  connected: boolean;
  theme: ThemeMode;
  thinking: boolean;
  draft: string;
  messages: ChatMessage[];
  schedules: ScheduleItem[];
  calendarFocusDate: string | null;
  calendarPulse: { date: string; count: number; token: number } | null;
  recommendedPlaces: MakersMapPlace[];
  mapTitle: string;
  mapRevision: number;
  scheduleViewDate: Date | null;
}

export type Action =
  | { type: 'SET_CONNECTED'; payload: boolean }
  | { type: 'SET_THEME'; payload: ThemeMode }
  | { type: 'SET_THINKING'; payload: boolean }
  | { type: 'SET_DRAFT'; payload: string }
  | { type: 'ADD_MESSAGE'; payload: ChatMessage }
  | { type: 'HYDRATE_MESSAGES'; payload: ChatMessage[] }
  | { type: 'UPDATE_MESSAGE'; payload: { id: string; patch: Partial<ChatMessage>; delta?: string } }
  | { type: 'SET_SCHEDULES'; payload: ScheduleItem[] }
  | { type: 'MERGE_SCHEDULES'; payload: ScheduleItem[] }
  | { type: 'FOCUS_CALENDAR'; payload: string }
  | { type: 'PULSE_CALENDAR'; payload: { date: string; count: number } }
  | { type: 'SET_MAP_PLACES'; payload: { places: MakersMapPlace[]; title?: string } }
  | { type: 'UPDATE_SCHEDULE'; payload: ScheduleItem }
  | { type: 'DELETE_SCHEDULE'; payload: string }
  | { type: 'SHOW_SCHEDULE_VIEW'; payload: Date | null }
  | { type: 'CLEAR_ALL_STREAMING'; payload: Record<string, never> };

export const initialState: AppState = {
  userId: 'local-user',
  conversationId: 'default-conversation',
  sessionId: 'local-user',
  connected: false,
  theme: initialTheme(),
  thinking: false,
  draft: '',
  messages: [],
  schedules: [],
  calendarFocusDate: null,
  calendarPulse: null,
  recommendedPlaces: [],
  mapTitle: '推荐地点',
  mapRevision: 0,
  scheduleViewDate: null,
};

export function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'SET_CONNECTED': return { ...state, connected: action.payload };
    case 'SET_THEME': return { ...state, theme: action.payload };
    case 'SET_THINKING': return { ...state, thinking: action.payload };
    case 'SET_DRAFT': return { ...state, draft: action.payload };
    case 'ADD_MESSAGE': return { ...state, messages: [...state.messages, action.payload] };
    case 'HYDRATE_MESSAGES': return { ...state, messages: action.payload };
    case 'UPDATE_MESSAGE':
      return {
        ...state,
        messages: state.messages.map((message) => {
          if (message.id !== action.payload.id) return message;
          if (action.payload.delta !== undefined) {
            return { ...message, ...action.payload.patch, content: message.content + action.payload.delta };
          }
          return { ...message, ...action.payload.patch };
        }),
      };
    case 'SET_SCHEDULES': return { ...state, schedules: action.payload };
    case 'MERGE_SCHEDULES': {
      const merged = new Map(state.schedules.map((item) => [item.id, item]));
      action.payload.forEach((item) => merged.set(item.id, item));
      return {
        ...state,
        schedules: Array.from(merged.values()).sort((a, b) => a.start_time - b.start_time),
      };
    }
    case 'FOCUS_CALENDAR':
      return { ...state, calendarFocusDate: action.payload };
    case 'PULSE_CALENDAR':
      return {
        ...state,
        calendarFocusDate: action.payload.date,
        calendarPulse: { ...action.payload, token: Date.now() },
      };
    case 'SET_MAP_PLACES':
      return {
        ...state,
        recommendedPlaces: action.payload.places,
        mapTitle: action.payload.title || '推荐地点',
        mapRevision: state.mapRevision + 1,
      };
    case 'UPDATE_SCHEDULE':
      return { ...state, schedules: state.schedules.map((item) => item.id === action.payload.id ? action.payload : item) };
    case 'DELETE_SCHEDULE': return { ...state, schedules: state.schedules.filter((item) => item.id !== action.payload) };
    case 'SHOW_SCHEDULE_VIEW': return { ...state, scheduleViewDate: action.payload };
    case 'CLEAR_ALL_STREAMING':
      return { ...state, messages: state.messages.map((message) => message.streaming ? { ...message, streaming: false } : message) };
    default: return state;
  }
}

export const AppStateContext = createContext<AppState | null>(null);
export const AppDispatchContext = createContext<Dispatch<Action> | null>(null);

export function useAppState(): AppState {
  const context = useContext(AppStateContext);
  if (!context) throw new Error('useAppState must be used within AppProvider');
  return context;
}

export function useAppDispatch(): Dispatch<Action> {
  const context = useContext(AppDispatchContext);
  if (!context) throw new Error('useAppDispatch must be used within AppProvider');
  return context;
}
