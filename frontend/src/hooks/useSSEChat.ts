import { useEffect, useRef } from 'react';
import { MessagePlugin } from 'tdesign-react';
import { bootstrapApp, saveConversationMessage } from '../services/api';
import { withEdgeOneAuth } from '../services/auth';
import { makersConversationHeaders } from '../services/conversation';
import { splitSseFrames } from '../services/sse';
import { useAppDispatch, useAppState } from '../store/appState';
import type { ChatMessage } from '../types';

type ClientEvent = { type: string; payload: Record<string, unknown> };

class SSEChatClient {
  private controller: AbortController | null = null;
  private listeners = new Set<(message: ClientEvent) => void>();

  constructor(private readonly conversationId: string) {}

  private emit(message: ClientEvent) {
    for (const listener of this.listeners) listener(message);
  }

  on(listener: (message: ClientEvent) => void) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  connect() {
    // SSE opens one request per message; no persistent socket is required.
  }

  async stop(): Promise<void> {
    this.controller?.abort();
    this.controller = null;
    try {
      await fetch(withEdgeOneAuth('/stop'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...makersConversationHeaders(this.conversationId),
        },
        body: JSON.stringify({ conversation_id: this.conversationId }),
        credentials: 'same-origin',
      });
    } catch {
      // Best-effort cancellation; the aborted request signal is the first line of defence.
    }
  }

  async send(rawMessage: unknown) {
    const message = rawMessage as { type?: string; payload?: Record<string, unknown> };
    if (message.type === 'ping') return;

    if (this.controller) await this.stop();
    this.controller = new AbortController();
    const signal = this.controller.signal;
    const streamId = `ai-stream-${Date.now()}`;
    let streamFinished = false;

    const finish = () => {
      if (streamFinished) return;
      streamFinished = true;
      this.emit({ type: 'stream_end', payload: { id: streamId } });
    };

    this.emit({ type: 'stream_start', payload: { id: streamId, intent: 'chat' } });

    try {
      const response = await fetch(withEdgeOneAuth('/chat'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...makersConversationHeaders(this.conversationId),
        },
        body: JSON.stringify(message.payload || {}),
        signal,
        credentials: 'same-origin',
      });

      if (!response.ok) {
        let detail = `HTTP ${response.status}`;
        try {
          const data = await response.json() as { error?: string; detail?: string };
          detail = data.error || data.detail || detail;
        } catch {
          // Keep the HTTP status fallback.
        }
        throw new Error(detail);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('无法读取响应流');

      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parsed = splitSseFrames(buffer);
        buffer = parsed.rest;

        for (const frame of parsed.frames) {
          if (frame === '[DONE]') {
            finish();
            return;
          }
          try {
            const event = JSON.parse(frame) as Record<string, unknown>;
            switch (String(event.type || '')) {
              case 'ai_response':
                this.emit({
                  type: 'stream_delta',
                  payload: {
                    id: streamId,
                    delta: typeof event.content === 'string' ? event.content : '',
                  },
                });
                break;
              case 'tool_call':
                this.emit({
                  type: 'search_status',
                  payload: {
                    id: streamId,
                    status: 'searching',
                    statusText: event.name === 'web_search'
                      ? '正在联网搜索…'
                      : `正在调用 ${String(event.name || '工具')}…`,
                  },
                });
                break;
              case 'tool_result':
                this.emit({
                  type: 'search_status',
                  payload: { id: streamId, status: 'analyzing', statusText: '工具已返回，正在整理…' },
                });
                break;
              case 'error_message':
                this.emit({
                  type: 'error',
                  payload: { message: typeof event.content === 'string' ? event.content : '服务异常' },
                });
                break;
              case 'ping':
              case 'usage':
                break;
            }
          } catch {
            // Ignore malformed or non-JSON events without breaking later frames.
          }
        }
      }
      finish();
    } catch (error) {
      if ((error as Error).name !== 'AbortError') {
        this.emit({
          type: 'error',
          payload: { message: (error as Error).message || '请求失败' },
        });
      }
      finish();
    } finally {
      if (this.controller?.signal === signal) this.controller = null;
    }
  }

  close() {
    void this.stop();
  }
}

export function useSSEChat() {
  const { conversationId } = useAppState();
  const dispatch = useAppDispatch();
  const clientRef = useRef<SSEChatClient | null>(null);
  const streamMessages = useRef<Map<string, ChatMessage>>(new Map());

  useEffect(() => {
    const client = new SSEChatClient(conversationId);
    clientRef.current = client;
    let disposed = false;

    const persist = (message: ChatMessage) => {
      void saveConversationMessage(conversationId, message).catch((error) => {
        console.warn('message persistence failed', error);
      });
    };

    const off = client.on((message) => {
      switch (message.type) {
        case 'stream_start': {
          dispatch({ type: 'SET_THINKING', payload: false });
          const id = String(message.payload.id || `ai-stream-${Date.now()}`);
          const streamMessage: ChatMessage = {
            id,
            role: 'ai',
            content: '',
            ts: Date.now(),
            streaming: true,
            skill: {
              intent: 'chat',
              mode: 'immediate',
              content: '',
              icon: '✨',
              action_label: '',
              params: {},
              data: { status: 'thinking', statusText: '思考中…' },
            },
          };
          streamMessages.current.set(id, streamMessage);
          dispatch({ type: 'ADD_MESSAGE', payload: streamMessage });
          break;
        }
        case 'stream_delta': {
          const id = String(message.payload.id || '');
          const delta = String(message.payload.delta || '');
          const current = streamMessages.current.get(id);
          if (current && delta) {
            streamMessages.current.set(id, { ...current, content: current.content + delta });
            dispatch({ type: 'UPDATE_MESSAGE', payload: { id, patch: {}, delta } });
          }
          break;
        }
        case 'stream_end': {
          const id = String(message.payload.id || '');
          const current = streamMessages.current.get(id);
          if (current) {
            persist({ ...current, streaming: false });
            streamMessages.current.delete(id);
          }
          dispatch({ type: 'UPDATE_MESSAGE', payload: { id, patch: { streaming: false } } });
          break;
        }
        case 'search_status': {
          const id = String(message.payload.id || '');
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
                  data: {
                    status: String(message.payload.status || 'searching'),
                    statusText: String(message.payload.statusText || '正在搜索…'),
                  },
                },
              },
            },
          });
          break;
        }
        case 'error':
          dispatch({ type: 'SET_THINKING', payload: false });
          MessagePlugin.error(String(message.payload.message || '服务异常'));
          break;
      }
    });

    void bootstrapApp(conversationId)
      .then((data) => {
        if (!disposed) dispatch({ type: 'HYDRATE_MESSAGES', payload: data.messages });
      })
      .catch((error) => console.warn('bootstrap failed', error))
      .finally(() => dispatch({ type: 'SET_CONNECTED', payload: true }));

    return () => {
      disposed = true;
      off();
      client.close();
    };
  }, [conversationId, dispatch]);

  return clientRef;
}
