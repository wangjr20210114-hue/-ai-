import type { RichMediaAsset } from '../../../types';
import {
  initialChatControllerState,
  type ChatControllerState,
} from './state';


export type ChatControllerEvent =
  | { type: 'stage'; payload: { stage?: string } }
  | { type: 'token'; content?: string; reasoning_content?: never }
  | { type: 'media'; payload: { media?: RichMediaAsset[] } }
  | { type: 'done' }
  | { type: 'error'; error?: string }
  | { type: string; [key: string]: unknown };

export function reduceChatControllerEvent(
  state: ChatControllerState = initialChatControllerState,
  event: ChatControllerEvent,
): ChatControllerState {
  if (event.type === 'stage') {
    const payload = 'payload' in event && event.payload
      ? event.payload as { stage?: string }
      : {};
    return {
      ...state,
      progress: { stage: String(payload.stage || state.progress.stage) },
    };
  }
  if (event.type === 'token') {
    return {
      ...state,
      streamingText: state.streamingText + String(
        'content' in event ? event.content || '' : '',
      ),
    };
  }
  if (event.type === 'media') {
    const payload = 'payload' in event && event.payload
      ? event.payload as { media?: RichMediaAsset[] }
      : {};
    return {
      ...state,
      search: {
        media: Array.isArray(payload.media) ? payload.media : state.search.media,
      },
    };
  }
  if (event.type === 'done') return { ...state, terminal: 'done', error: '' };
  if (event.type === 'error') {
    return {
      ...state,
      terminal: 'error',
      error: String('error' in event ? event.error || 'stream_error' : 'stream_error'),
    };
  }
  return state;
}
