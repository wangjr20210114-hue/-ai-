import { useEffect, useRef } from 'react';
import { MessagePlugin } from 'tdesign-react';
import { WSClient } from '../services/websocket';
import { bootstrapApp, saveConversationMessage } from '../services/api';
import { useAppDispatch, useAppState } from '../store/appState';
import type { WSMessage, SkillInfo, PaperInfo, ChatMessage } from '../types';

/** 建立 WebSocket 连接并把消息分发到全局状态。 */
export function useWebSocket() {
  const { conversationId } = useAppState();
  const dispatch = useAppDispatch();
  const clientRef = useRef<WSClient | null>(null);
  const streamingIds = useRef<Set<string>>(new Set());
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
          const message: ChatMessage = {
            id: msgId,
            role: 'ai',
            content: msg.payload.content || '',
            ts: Date.now(),
          };
          dispatch({
            type: 'ADD_MESSAGE',
            payload: message,
          });
          persist(message);
          break;
        }

        // === 流式输出 ===
        case 'stream_start': {
          dispatch({ type: 'SET_THINKING', payload: false });
          const id = msg.payload.id || 'ai-stream-' + Date.now();
          streamingIds.current.add(id);
          const intent = msg.payload.intent || '';
          const iconMap: Record<string, string> = {
            paper: '📄', image: '🎨', search: '🔍', translation: '🔤', chat: '✨',
          };
          const streamMessage: ChatMessage = {
            id,
            role: 'ai',
            content: '',
            ts: Date.now(),
            streaming: true,
            skill: intent ? {
              intent,
              mode: 'immediate',
              content: '',
              icon: iconMap[intent] || '✨',
              action_label: '',
              params: {},
              data: msg.payload.status ? { status: msg.payload.status } : {},
            } : undefined,
          };
          streamMessages.current.set(id, streamMessage);
          dispatch({
            type: 'ADD_MESSAGE',
            payload: streamMessage,
          });
          break;
        }

        // === 搜索进度状态 ===
        case 'search_status': {
          const id = msg.payload.id;
          if (!id) break;
          const status = msg.payload.status;
          if (status === 'thinking') {
            const searchResults = msg.payload.search_results;
            const current = streamMessages.current.get(id);
            if (current) {
              streamMessages.current.set(id, {
                ...current,
                skill: undefined,
                searchResults: searchResults && searchResults.total > 0 ? searchResults : undefined,
              });
            }
            // 切换到流式输出模式
            dispatch({
              type: 'UPDATE_MESSAGE',
              payload: {
                id,
                patch: {
                  skill: undefined,
                  searchResults: searchResults && searchResults.total > 0 ? searchResults : undefined,
                },
                delta: '',
              },
            });
          } else {
            const current = streamMessages.current.get(id);
            if (current) {
              streamMessages.current.set(id, {
                ...current,
                skill: { intent: 'search', mode: 'immediate', content: '', icon: '🔍', action_label: '', params: {}, data: { status: 'searching', statusText: status } },
              });
            }
            // 更新搜索状态文案
            dispatch({
              type: 'UPDATE_MESSAGE',
              payload: {
                id,
                patch: {
                  skill: {
                    intent: 'search',
                    mode: 'immediate',
                    content: '',
                    icon: '🔍',
                    action_label: '',
                    params: {},
                    data: { status: 'searching', statusText: status },
                  },
                  // 如果有来源信息，提前存入
                  ...(msg.payload.search_results ? {
                    searchResults: msg.payload.search_results,
                  } : {}),
                },
              },
            });
          }
          break;
        }

        case 'stream_delta': {
          const id = msg.payload.id;
          if (!id) break;
          const delta = msg.payload.delta || '';
          if (delta) {
            const current = streamMessages.current.get(id);
            if (current) streamMessages.current.set(id, { ...current, content: current.content + delta });
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
          if (!id) break;
          streamingIds.current.delete(id);
          const papers: PaperInfo[] | undefined = msg.payload.papers;
          const imageUrl: string | undefined = msg.payload.image_url;
          const searchResults = msg.payload.search_results;
          const imageDelta = imageUrl ? `\n\n![${msg.payload.image_prompt || '生成的图片'}](${imageUrl})` : '';
          const current = streamMessages.current.get(id);
          if (current) {
            const completed: ChatMessage = {
              ...current,
              content: current.content + imageDelta,
              streaming: false,
              papers: papers && papers.length > 0 ? papers : undefined,
              searchResults: searchResults && searchResults.total > 0 ? searchResults : undefined,
              followUps: msg.payload.follow_ups && msg.payload.follow_ups.length > 0 ? msg.payload.follow_ups : undefined,
            };
            streamMessages.current.delete(id);
            persist(completed);
          }

          dispatch({
            type: 'UPDATE_MESSAGE',
            payload: {
              id,
              patch: {
                streaming: false,
                papers: papers && papers.length > 0 ? papers : undefined,
                searchResults: searchResults && searchResults.total > 0 ? searchResults : undefined,
                followUps: msg.payload.follow_ups && msg.payload.follow_ups.length > 0
                  ? msg.payload.follow_ups
                  : undefined,
                // 生图结果：用 markdown 图片格式追加到 content
                ...(imageUrl ? {} : {}),
              },
              delta: imageUrl ? `\n\n![${msg.payload.image_prompt || '生成的图片'}](${imageUrl})` : undefined,
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
          const savedMessage: ChatMessage = {
            id: msgId,
            role: 'ai',
            content: skill.content,
            ts: Date.now(),
            skill,
            followUps: s.follow_ups && s.follow_ups.length > 0 ? s.follow_ups : undefined,
            autoShowTravelAssistant: skill.intent === 'travel' && skill.mode === 'auto',
          };

          if (skill.mode === 'immediate') {
            dispatch({
              type: 'ADD_MESSAGE',
              payload: savedMessage,
            });
            persist(savedMessage);
            return;
          }

          dispatch({
            type: 'ADD_MESSAGE',
            payload: savedMessage,
          });
          persist(savedMessage);
          return;
        }

        case 'error':
          dispatch({ type: 'SET_THINKING', payload: false });
          // 额度耗尽 → 清除所有流式状态并显示醒目错误
          if (msg.payload.error_type === 'quota_exhausted') {
            streamingIds.current.clear();
            // 将所有正在流式的消息标记为已结束
            dispatch({ type: 'CLEAR_ALL_STREAMING', payload: {} });
            MessagePlugin.error({
              content: msg.payload.message || 'API 额度已用尽，请稍后再试',
              duration: 5000,
            });
          } else {
            MessagePlugin.error(msg.payload.message || '服务异常');
          }
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  return clientRef;
}
