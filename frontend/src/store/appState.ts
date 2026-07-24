import { createContext, useContext, type Dispatch } from 'react';
import type {
  ChatMessage,
  ThemeMode,
  TravelPlan,
  ScheduleItem,
  MakersMapPlace,
  ConversationSummary,
  ProactiveState,
  DocumentContext,
} from '../types';
import { translate } from '../i18n';

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
  documentContext: DocumentContext | null;
  messages: ChatMessage[];
  plans: TravelPlan[];
  schedules: ScheduleItem[];
  mapPlaces: MakersMapPlace[];
  mapTitle: string;
  mapRevision: number;
  calendarPulse: { date: string; count: number; token: number } | null;
  conversations: ConversationSummary[];
  scheduleViewDate: Date | null;
  proactive: ProactiveState | null;
}

export type Action =
  | { type: 'SET_CONNECTED'; payload: boolean }
  | { type: 'SET_CONVERSATION_ID'; payload: string }
  | { type: 'SET_CONVERSATIONS'; payload: ConversationSummary[] }
  | { type: 'UPSERT_CONVERSATION'; payload: ConversationSummary }
  | { type: 'SET_THEME'; payload: ThemeMode }
  | { type: 'SET_THINKING'; payload: boolean }
  | { type: 'SET_DRAFT'; payload: string }
  | { type: 'SET_DOCUMENT_CONTEXT'; payload: DocumentContext | null }
  | { type: 'ADD_MESSAGE'; payload: ChatMessage }
  | { type: 'HYDRATE_MESSAGES'; payload: ChatMessage[] }
  | { type: 'UPDATE_MESSAGE'; payload: { id: string; patch: Partial<ChatMessage>; delta?: string } }
  | { type: 'SET_PLANS'; payload: TravelPlan[] }
  | { type: 'ADD_PLAN'; payload: TravelPlan }
  | { type: 'UPDATE_PLAN'; payload: TravelPlan }
  | { type: 'DELETE_PLAN'; payload: string }
  | { type: 'SET_SCHEDULES'; payload: ScheduleItem[] }
  | { type: 'MERGE_SCHEDULES'; payload: ScheduleItem[] }
  | { type: 'SET_MAP_PLACES'; payload: { places: MakersMapPlace[]; title?: string; reveal?: boolean } }
  | { type: 'PULSE_CALENDAR'; payload: { date: string; count: number } }
  | { type: 'CLEAR_CALENDAR_PULSE'; payload: Record<string, never> }
  | { type: 'HYDRATE_WORKSPACE'; payload: { schedules?: ScheduleItem[]; mapPlaces?: MakersMapPlace[]; mapTitle?: string } }
  | { type: 'ADD_SCHEDULE'; payload: ScheduleItem }
  | { type: 'UPDATE_SCHEDULE'; payload: ScheduleItem }
  | { type: 'DELETE_SCHEDULE'; payload: string }
  | { type: 'SHOW_SCHEDULE_VIEW'; payload: Date | null }
  | { type: 'HYDRATE_PROACTIVE'; payload: ProactiveState }
  | { type: 'CLEAR_ALL_STREAMING'; payload: Record<string, never> };

export const initialState: AppState = {
  userId: 'local-user',
  conversationId: 'default-conversation',
  sessionId: 'local-user',
  connected: false,
  theme: initialTheme(),
  thinking: false,
  draft: '',
  documentContext: null,
  messages: [],
  plans: [],
  schedules: [],
  mapPlaces: [],
  mapTitle: translate('relatedPlaces'),
  mapRevision: 0,
  calendarPulse: null,
  conversations: [],
  scheduleViewDate: null,
  proactive: null,
};

function sameMapPlaces(current: MakersMapPlace[], next: MakersMapPlace[]): boolean {
  if (current === next) return true;
  if (current.length !== next.length) return false;
  return current.every((place, index) => {
    const candidate = next[index];
    return Boolean(candidate)
      && place.place_id === candidate.place_id
      && place.provider === candidate.provider
      && place.name === candidate.name
      && place.address === candidate.address
      && place.latitude === candidate.latitude
      && place.longitude === candidate.longitude;
  });
}

export function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'SET_CONNECTED': return { ...state, connected: action.payload };
    case 'SET_CONVERSATION_ID':
      return {
        ...state,
        conversationId: action.payload,
        connected: false,
        thinking: false,
        draft: '',
        documentContext: null,
        messages: [],
        plans: [],
        scheduleViewDate: null,
      };
    case 'SET_CONVERSATIONS': return { ...state, conversations: action.payload };
    case 'UPSERT_CONVERSATION': {
      const conversations = [
        action.payload,
        ...state.conversations.filter((item) => item.id !== action.payload.id),
      ].sort((a, b) => b.updatedAt - a.updatedAt);
      return { ...state, conversations };
    }
    case 'SET_THEME': return { ...state, theme: action.payload };
    case 'SET_THINKING': return { ...state, thinking: action.payload };
    case 'SET_DRAFT': return { ...state, draft: action.payload };
    case 'SET_DOCUMENT_CONTEXT': return { ...state, documentContext: action.payload };
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
    case 'SET_PLANS': return { ...state, plans: action.payload };
    case 'ADD_PLAN': return { ...state, plans: [action.payload, ...state.plans] };
    case 'UPDATE_PLAN':
      return { ...state, plans: state.plans.map((plan) => plan.id === action.payload.id ? action.payload : plan) };
    case 'DELETE_PLAN': return { ...state, plans: state.plans.filter((plan) => plan.id !== action.payload) };
    case 'SET_SCHEDULES': return { ...state, schedules: action.payload };
    case 'MERGE_SCHEDULES': {
      const merged = new Map(state.schedules.map((item) => [item.id, item]));
      action.payload.forEach((item) => merged.set(item.id, item));
      return { ...state, schedules: Array.from(merged.values()).sort((a, b) => a.start_time - b.start_time) };
    }
    case 'SET_MAP_PLACES': {
      const nextTitle = action.payload.title || translate('relatedPlaces');
      const placesChanged = !sameMapPlaces(state.mapPlaces, action.payload.places);
      return {
        ...state,
        mapPlaces: placesChanged ? action.payload.places : state.mapPlaces,
        mapTitle: nextTitle,
        mapRevision: placesChanged || action.payload.reveal ? state.mapRevision + 1 : state.mapRevision,
      };
    }
    case 'PULSE_CALENDAR':
      return { ...state, calendarPulse: { ...action.payload, token: Date.now() } };
    case 'CLEAR_CALENDAR_PULSE':
      return { ...state, calendarPulse: null };
    case 'HYDRATE_WORKSPACE': {
      const hasMapSnapshot = action.payload.mapPlaces !== undefined;
      const nextPlaces = hasMapSnapshot ? action.payload.mapPlaces || [] : state.mapPlaces;
      const placesChanged = hasMapSnapshot && !sameMapPlaces(state.mapPlaces, nextPlaces);
      return {
        ...state,
        schedules: action.payload.schedules || [],
        mapPlaces: placesChanged ? nextPlaces : state.mapPlaces,
        mapTitle: hasMapSnapshot ? action.payload.mapTitle || translate('relatedPlaces') : state.mapTitle,
        mapRevision: placesChanged ? state.mapRevision + 1 : state.mapRevision,
      };
    }
    case 'ADD_SCHEDULE': return { ...state, schedules: [action.payload, ...state.schedules] };
    case 'UPDATE_SCHEDULE':
      return { ...state, schedules: state.schedules.map((item) => item.id === action.payload.id ? action.payload : item) };
    case 'DELETE_SCHEDULE': return { ...state, schedules: state.schedules.filter((item) => item.id !== action.payload) };
    case 'SHOW_SCHEDULE_VIEW': return { ...state, scheduleViewDate: action.payload };
    case 'HYDRATE_PROACTIVE': return { ...state, proactive: action.payload };
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
