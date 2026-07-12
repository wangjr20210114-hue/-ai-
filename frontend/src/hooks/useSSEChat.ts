import { useEffect, useRef } from 'react';
import { MessagePlugin } from 'tdesign-react';
import { bootstrapApp, saveConversationMessage } from '../services/api';
import { useAppDispatch, useAppState } from '../store/appState';
import type { SkillInfo, PaperInfo, ChatMessage } from '../types';

/** Generate or get EdgeOne conversation ID. */
function getOrCreateConversationId(): string {
  const key = 'eo_conv_id';
  let id = localStorage.getItem(key);
  if (!id) {
    id = crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    localStorage.setItem(key, id);
  }
  return id;
}

/** Extract EdgeOne auth params from current URL for API calls. */
function getEoAuthParams(): string {
  const p = new URLSearchParams(window.location.search);
  const token = p.get('eo_token');
  const time = p.get('eo_time');
  if (token && time) return `?eo_token=${token}&eo_time=${time}`;
  return '';
}

/** SSE-based chat client — same interface as WSClient. */
class SSEChatClient {
  private controller: AbortController | null = null;
  private listeners = new Set<(msg: any) => void>();
  private convId: string;
  private authParams: string;

  constructor() {
    this.convId = getOrCreateConversationId();
    this.authParams = getEoAuthParams();
  }

  get conversationId() {
    return this.convId;
  }

  /** Simulates WSClient.send() — POST /chat with SSE. */
  async send(msg: any) {
    // Handle ping internally (EdgeOne agent has its own heartbeat)
    if (msg.type === 'ping') return;

    const body = msg.payload || {};
    this.controller?.abort();
    this.controller = new AbortController();
    const signal = this.controller.signal;

    try {
      const resp = await fetch(`/chat${this.authParams}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'makers-conversation-id': this.convId,
        },
        body: JSON.stringify(body),
        signal,
      });

      if (!resp.ok) {
        this.emit({ type: 'error', payload: { message: `HTTP ${resp.status}` } });
        return;
      }

      const reader = resp.body?.getReader();
      if (!reader) {
        this.emit({ type: 'error', payload: { message: '无法读取响应流' } });
        return;
      }

      const decoder = new TextDecoder();
      let buffer = '';
      let streamId = '';
      let intent = 'chat';

      // Start streaming with default "thinking" state
      streamId = 'ai-stream-' + Date.now();
      this.emit({
        type: 'stream_start',
        payload: { id: streamId, intent: 'search' },
      });

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (raw === '[DONE]') {
            this.emit({ type: 'stream_end', payload: { id: streamId } });
            return;
          }

          try {
            const event = JSON.parse(raw);
            switch (event.type) {
              case 'ai_response':
                this.emit({
                  type: 'stream_delta',
                  payload: { id: streamId, delta: event.content },
                });
                break;

              case 'tool_call': {
                // Show search status when tool is called
                const name = event.name || '';
                if (name === 'search_web' || name === 'search_images') {
                  this.emit({
                    type: 'search_status',
                    payload: {
                      id: streamId,
                      status: 'searching',
                      statusText: `正在搜索…`,
                    },
                  });
                }
                break;
              }

              case 'tool_result': {
                if (event.name === 'search_web') {
                  this.emit({
                    type: 'search_status',
                    payload: {
                      id: streamId,
                      status: 'analyzing',
                      statusText: '找到结果，正在整理…',
                    },
                  });
                }
                break;
              }

              case 'ping':
                // Ignore heartbeats
                break;

              case 'error_message':
                this.emit({
                  type: 'error',
                  payload: { message: event.content },
                });
                break;
            }
          } catch {
            // Skip non-JSON lines
          }
        }
      }

      // Stream ended without [DONE]
      this.emit({ type: 'stream_end', payload: { id: streamId } });
    } catch (err: any) {
      if (err.name === 'AbortError') return;
      this.emit({
        type: 'error',
        payload: { message: err.message || '请求失败' },
      });
    }
  }

  on(listener: (msg: any) => void) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private emit(msg: any) {
    for (const fn of this.listeners) fn(msg);
  }

  close() {
    this.controller?.abort();
    this.controller = null;
  }

  connect() {
    // SSE doesn't need explicit connect — sends on each request
  }
}

/** Hook that replaces useWebSocket() with SSE-based client. */
export function useSSEChat() {
  const { conversationId } = useAppState();
  const dispatch = useAppDispatch();
  const clientRef = useRef<SSEChatClient | null>(null);
  const streamMessages = useRef<Map<string, ChatMessage>>(new Map());
  const streamingIds = useRef<Set<string>>(new Set());

  useEffect(() => {
    const client = new SSEChatClient();
    clientRef.current = client;
    let disposed = false;

    const persist = (message: ChatMessage) => {
      void saveConversationMessage(conversationId, message).catch((error) => {
        console.warn('message persistence failed', error);
      });
    };

    const off = client.on((msg: any) => {
      switch (msg.type) {
        case 'stream_start': {
          dispatch({ type: 'SET_THINKING', payload: false });
          const id = msg.payload.id || 'ai-stream-' + Date.now();
          streamingIds.current.add(id);
          const streamMessage: ChatMessage = {
            id,
            role: 'ai',
            content: '',
            ts: Date.now(),
            streaming: true,
            skill: {
              intent: 'search',
              mode: 'immediate',
              content: '',
              icon: '🔍',
              action_label: '',
              params: {},
              data: { status: 'searching', statusText: '思考中…' },
            },
          };
          streamMessages.current.set(id, streamMessage);
          dispatch({ type: 'ADD_MESSAGE', payload: streamMessage });
          break;
        }

        case 'stream_delta': {
          const id = msg.payload.id;
          if (!id) break;
          const delta = msg.payload.delta || '';
          if (delta) {
            const current = streamMessages.current.get(id);
            if (current)
              streamMessages.current.set(id, { ...current, content: current.content + delta });
            dispatch({ type: 'UPDATE_MESSAGE', payload: { id, patch: {}, delta } });
          }
          break;
        }

        case 'stream_end': {
          const id = msg.payload.id;
          if (!id) break;
          streamingIds.current.delete(id);
          const current = streamMessages.current.get(id);
          if (current) {
            const completed: ChatMessage = { ...current, streaming: false };
            streamMessages.current.delete(id);
            persist(completed);
          }
          dispatch({
            type: 'UPDATE_MESSAGE',
            payload: { id, patch: { streaming: false } },
          });
          break;
        }

        case 'search_status': {
          const id = msg.payload.id;
          if (!id) break;
          const statusText = msg.payload.statusText || '正在搜索…';
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
                  data: { status: 'searching', statusText },
                },
              },
            },
          });
          break;
        }

        case 'error': {
          dispatch({ type: 'SET_THINKING', payload: false });
          MessagePlugin.error(msg.payload.message || '服务异常');
          break;
        }
      }
    });

    void bootstrapApp(conversationId)
      .then((data) => {
        if (!disposed) dispatch({ type: 'HYDRATE_MESSAGES', payload: data.messages });
      })
      .catch((error) => console.warn('bootstrap failed', error))
      .finally(() => {
        dispatch({ type: 'SET_CONNECTED', payload: true });
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
