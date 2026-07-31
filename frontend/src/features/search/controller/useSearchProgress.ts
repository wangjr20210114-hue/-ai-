import { useReducer } from 'react';

import type { ChatControllerEvent } from '../../chat/model/events';
import { reduceChatControllerEvent } from '../../chat/model/events';
import { initialChatControllerState } from '../../chat/model/state';


export function useSearchProgress() {
  const [state, receive] = useReducer(
    reduceChatControllerEvent,
    initialChatControllerState,
  );
  return {
    progress: state.progress,
    media: state.search.media,
    receive: receive as (event: ChatControllerEvent) => void,
  };
}
