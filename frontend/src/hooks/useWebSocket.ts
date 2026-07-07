import { useEffect, useRef } from 'react';
import { MessagePlugin } from 'tdesign-react';
import { WSClient } from '../services/websocket';
import { useAppDispatch, useAppState } from '../store/AppContext';
import type { WSMessage, SkillInfo, PaperInfo } from '../types';

/** 建立 WebSocket 连接并把消息分发到全局状态。 */
export function useWebSocket() {
  const { sessionId } = useAppState();
  const dispatch = useAppDispatch();
  const clientRef = useRef<WSClient | null>(null);
  const streamingIds = useRef<Set<string>>(new Set());

  useEffect(() => {
    const client = new WSClient(sessionId);
    clientRef.current = client;

    const off = client.on((msg: WSMessage) => {
      switch (msg.type) {
        case 'ack':
          break;

        case 'chat_thinking':
          dispatch({ type: 'SET_THINKING', payload: true });
          break;

        case 'chat_reply': {
          dispatch({ type: 'SET_THINKING', payload: false });
          const msgId = 'ai-' + (msg.ts || Date.now());
          dispatch({
            type: 'ADD_MESSAGE',
            payload: {
              id: msgId,
              role: 'ai',
              content: msg.payload.content || '',
              ts: Date.now(),
            },
          });
          break;
        }

        // === 流式输出 ===
        case 'stream_start': {
          dispatch({ type: 'SET_THINKING', payload: false });
          const id = msg.payload.id || 'ai-stream-' + Date.now();
          streamingIds.current.add(id);
          dispatch({
            type: 'ADD_MESSAGE',
            payload: {
              id,
              role: 'ai',
              content: '',
              ts: Date.now(),
              streaming: true,
              skill: msg.payload.intent ? {
                intent: msg.payload.intent,
                mode: 'immediate',
                content: '',
                icon: msg.payload.intent === 'paper' ? '📄' : '✨',
                action_label: '',
                params: {},
                data: {},
              } : undefined,
            },
          });
          break;
        }

        case 'stream_delta': {
          const id = msg.payload.id;
          const delta = msg.payload.delta || '';
          if (delta) {
            dispatch({
              type: 'UPDATE_MESSAGE',
              payload: {
                id,
                patch: {},
                delta,
              },
            });
          }
          break;
        }

        case 'stream_end': {
          const id = msg.payload.id;
          streamingIds.current.delete(id);
          const papers: PaperInfo[] | undefined = msg.payload.papers;

          dispatch({
            type: 'UPDATE_MESSAGE',
            payload: {
              id,
              patch: {
                streaming: false,
                papers: papers && papers.length > 0 ? papers : undefined,
                followUps: msg.payload.follow_ups && msg.payload.follow_ups.length > 0
                  ? msg.payload.follow_ups
                  : undefined,
              },
            },
          });
          break;
        }

        // === 技能建议 ===
        case 'suggestion': {
          dispatch({ type: 'SET_THINKING', payload: false });
          const s = msg.payload;

          const skill: SkillInfo = {
            intent: s.intent || 'chat',
            mode: s.mode || 'suggest',
            content: s.content || '',
            icon: s.icon || '✨',
            action_label: s.action_label || '执行',
            params: s.params || {},
            data: s.data || {},
          };

          const msgId = 'ai-skill-' + (msg.ts || Date.now());

          if (skill.mode === 'immediate') {
            dispatch({
              type: 'ADD_MESSAGE',
              payload: {
                id: msgId,
                role: 'ai',
                content: skill.content,
                ts: Date.now(),
                skill,
                followUps: s.follow_ups && s.follow_ups.length > 0 ? s.follow_ups : undefined,
              },
            });
            return;
          }

          dispatch({
            type: 'ADD_MESSAGE',
            payload: {
              id: msgId,
              role: 'ai',
              content: skill.content,
              ts: Date.now(),
              skill,
              followUps: s.follow_ups && s.follow_ups.length > 0 ? s.follow_ups : undefined,
              autoShowTravelAssistant: skill.intent === 'travel' && skill.mode === 'auto',
            },
          });
          return;
        }

        case 'error':
          dispatch({ type: 'SET_THINKING', payload: false });
          MessagePlugin.error(msg.payload.message || '服务异常');
          break;
      }
    });

    client.connect(
      () => dispatch({ type: 'SET_CONNECTED', payload: true }),
      () => dispatch({ type: 'SET_CONNECTED', payload: false }),
    );

    return () => {
      off();
      client.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  return clientRef;
}
