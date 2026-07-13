import { useEffect, useRef } from 'react';
import { MessagePlugin } from 'tdesign-react';
import { bootstrapApp, saveConversationMessage } from '../services/api';
import type { ChatClient } from '../services/chatClient';
import { WSClient } from '../services/websocket';
import { useAppDispatch, useAppState } from '../store/appState';
import type { ChatMessage, PaperInfo, SkillInfo, WSMessage } from '../types';

/** Bind the legacy local UI to the FastAPI WebSocket contract. */
export function useWebSocket() {
  const { conversationId } = useAppState();
  const dispatch = useAppDispatch();
  const clientRef = useRef<ChatClient | null>(null);
  const streamMessages = useRef<Map<string, ChatMessage>>(new Map());

  useEffect(() => {
    const client = new WSClient(conversationId);
    clientRef.current = client;
    let disposed = false;
    const persist = (message: ChatMessage) => {
      void saveConversationMessage(conversationId, message).catch((error) => {
        console.warn('message persistence failed', error);
      });
    };

    const off = client.on((message: WSMessage) => {
      const payload = message.payload;
      switch (message.type) {
        case 'ack':
        case 'pong':
          break;
        case 'chat_thinking':
          dispatch({ type: 'SET_THINKING', payload: true });
          break;
        case 'chat_reply': {
          dispatch({ type: 'SET_THINKING', payload: false });
          const reply: ChatMessage = {
            id: `ai-${message.ts || Date.now()}`,
            role: 'ai',
            content: String(payload.content || ''),
            ts: Date.now(),
          };
          dispatch({ type: 'ADD_MESSAGE', payload: reply });
          persist(reply);
          break;
        }
        case 'stream_start': {
          dispatch({ type: 'SET_THINKING', payload: false });
          const id = String(payload.id || `ai-stream-${Date.now()}`);
          const intent = String(payload.intent || 'chat');
          const icons: Record<string, string> = {
            paper: '📄', image: '🎨', search: '🔍', translation: '🔤', chat: '✨',
          };
          const streamMessage: ChatMessage = {
            id,
            role: 'ai',
            content: '',
            ts: Date.now(),
            streaming: true,
            skill: {
              intent,
              mode: 'immediate',
              content: '',
              icon: icons[intent] || '✨',
              action_label: '',
              params: {},
              data: payload.status ? { status: payload.status } : {},
            },
          };
          streamMessages.current.set(id, streamMessage);
          dispatch({ type: 'ADD_MESSAGE', payload: streamMessage });
          break;
        }
        case 'search_status': {
          const id = String(payload.id || '');
          if (!id) break;
          const status = String(payload.status || 'searching');
          const nested = payload.data && typeof payload.data === 'object'
            ? payload.data as Record<string, unknown>
            : {};
          const statusText = String(nested.statusText || payload.statusText || '正在搜索…');
          const current = streamMessages.current.get(id);
          const searchResults = payload.search_results;
          const skill = status === 'thinking' ? undefined : {
            intent: 'search', mode: 'immediate', content: '', icon: '🔍',
            action_label: '', params: {}, data: { status, statusText },
          };
          if (current) {
            streamMessages.current.set(id, {
              ...current,
              skill,
              searchResults: searchResults?.total ? searchResults : current.searchResults,
            });
          }
          dispatch({
            type: 'UPDATE_MESSAGE',
            payload: {
              id,
              patch: {
                skill,
                ...(searchResults?.total ? { searchResults } : {}),
              },
            },
          });
          break;
        }
        case 'stream_delta': {
          const id = String(payload.id || '');
          const delta = String(payload.delta || '');
          const current = streamMessages.current.get(id);
          if (current && delta) {
            streamMessages.current.set(id, { ...current, content: current.content + delta });
            dispatch({ type: 'UPDATE_MESSAGE', payload: { id, patch: {}, delta } });
          }
          break;
        }
        case 'stream_end': {
          const id = String(payload.id || '');
          const current = streamMessages.current.get(id);
          const papers = payload.papers as PaperInfo[] | undefined;
          const imageUrl = typeof payload.image_url === 'string' ? payload.image_url : '';
          const imageDelta = imageUrl
            ? `\n\n![${String(payload.image_prompt || '生成的图片')}](${imageUrl})`
            : '';
          if (current) {
            persist({
              ...current,
              content: current.content + imageDelta,
              streaming: false,
              papers: papers?.length ? papers : undefined,
              searchResults: payload.search_results?.total ? payload.search_results : undefined,
              followUps: payload.follow_ups?.length ? payload.follow_ups : undefined,
            });
            streamMessages.current.delete(id);
          }
          dispatch({
            type: 'UPDATE_MESSAGE',
            payload: {
              id,
              patch: {
                streaming: false,
                papers: papers?.length ? papers : undefined,
                searchResults: payload.search_results?.total ? payload.search_results : undefined,
                followUps: payload.follow_ups?.length ? payload.follow_ups : undefined,
              },
              delta: imageDelta || undefined,
            },
          });
          break;
        }
        case 'suggestion': {
          dispatch({ type: 'SET_THINKING', payload: false });
          const skill: SkillInfo = {
            intent: String(payload.intent || 'chat'),
            mode: String(payload.mode || 'suggest'),
            content: String(payload.content || ''),
            icon: String(payload.icon || '✨'),
            action_label: String(payload.action_label || '执行'),
            params: payload.params || {},
            data: payload.data || {},
          };
          const suggestion: ChatMessage = {
            id: `ai-skill-${message.ts || Date.now()}`,
            role: 'ai',
            content: skill.content,
            ts: Date.now(),
            skill,
            followUps: payload.follow_ups?.length ? payload.follow_ups : undefined,
            autoShowTravelAssistant: skill.intent === 'travel' && skill.mode === 'auto',
          };
          dispatch({ type: 'ADD_MESSAGE', payload: suggestion });
          persist(suggestion);
          break;
        }
        case 'error':
          dispatch({ type: 'SET_THINKING', payload: false });
          if (payload.error_type === 'quota_exhausted') {
            dispatch({ type: 'CLEAR_ALL_STREAMING', payload: {} });
          }
          MessagePlugin.error(String(payload.message || '服务异常'));
          break;
      }
    });

    void bootstrapApp(conversationId)
      .then((data) => {
        if (!disposed) dispatch({ type: 'HYDRATE_MESSAGES', payload: data.messages });
      })
      .catch((error) => console.warn('conversation bootstrap failed', error))
      .finally(() => {
        if (!disposed) {
          client.connect(
            () => dispatch({ type: 'SET_CONNECTED', payload: true }),
            () => dispatch({ type: 'SET_CONNECTED', payload: false }),
          );
        }
      });

    return () => {
      disposed = true;
      off();
      client.close();
    };
  }, [conversationId, dispatch]);

  return clientRef;
}
