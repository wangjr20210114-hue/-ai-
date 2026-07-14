import { useEffect, useRef } from 'react';
import { MessagePlugin } from 'tdesign-react';
import { bootstrapApp } from '../services/api';
import { withEdgeOneAuth } from '../services/auth';
import { makersConversationHeaders } from '../services/conversation';
import { stripInlineFollowUpSection } from '../services/chatContent';
import { splitSseFrames } from '../services/sse';
import { normalizeSearchMeta } from '../services/search';
import { useAppDispatch, useAppState } from '../store/appState';
import type { ChatMessage, MakersMapPlace, ScheduleItem } from '../types';

type ClientEvent = { type: string; payload: Record<string, unknown> };

const SEARCH_PROGRESS_LABELS: Record<string, string> = {
  searching: '正在互联网里捞点靠谱线索…',
  place_intent: '正在把目的地从这句话里请出来…',
  place_database: '正在给地点们挨个验明正身…',
  place_results: '地点已到齐，正在排队组成行程…',
  sources_found: '抓到一些线索，正在看看谁更靠谱…',
  fetching_page: '正在翻资料，先把水分拧一拧…',
  selecting_media: '文字看完了，图片也得过安检…',
  reviewing_media: '正在盯图检查，广告休想混进来…',
  composing: '材料齐活，正在摆成好读的样子…',
};

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
                      ? '正在查找相关信息…'
                      : '正在处理相关信息…',
                  },
                });
                break;
              case 'search_progress':
                {
                  const stage = String(event.stage || 'searching');
                this.emit({
                  type: 'search_status',
                  payload: {
                    id: streamId,
                    status: stage,
                    statusText: SEARCH_PROGRESS_LABELS[stage] || '正在处理相关信息…',
                  },
                });
                }
                break;
              case 'tool_result':
                {
                  const searchResults = normalizeSearchMeta(event.search_results);
                this.emit({
                  type: 'search_status',
                  payload: {
                    id: streamId,
                    status: 'analyzing',
                    statusText: '资料已核对，正在整理结果…',
                    ...(searchResults ? { search_results: searchResults } : {}),
                  },
                });
                break;
                }
              case 'map_places':
                this.emit({
                  type: 'map_places',
                  payload: {
                    title: String(event.title || '推荐地点'),
                    places: Array.isArray(event.places) ? event.places : [],
                  },
                });
                break;
              case 'follow_ups':
                this.emit({
                  type: 'follow_ups',
                  payload: {
                    id: streamId,
                    items: Array.isArray(event.items)
                      ? event.items.filter(item => typeof item === 'string').slice(0, 3)
                      : [],
                  },
                });
                break;
              case 'travel_plan':
                this.emit({
                  type: 'travel_plan',
                  payload: {
                    id: streamId,
                    plan: event.plan && typeof event.plan === 'object' ? event.plan : {},
                    schedules: Array.isArray(event.schedules) ? event.schedules : [],
                  },
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
  const { conversationId, userId } = useAppState();
  const dispatch = useAppDispatch();
  const clientRef = useRef<SSEChatClient | null>(null);
  const streamMessages = useRef<Map<string, ChatMessage>>(new Map());
  const suppressedInlineFollowUps = useRef<Set<string>>(new Set());

  useEffect(() => {
    const client = new SSEChatClient(conversationId);
    clientRef.current = client;
    let disposed = false;

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
          suppressedInlineFollowUps.current.delete(id);
          dispatch({ type: 'ADD_MESSAGE', payload: streamMessage });
          break;
        }
        case 'stream_delta': {
          const id = String(message.payload.id || '');
          const delta = String(message.payload.delta || '');
          const current = streamMessages.current.get(id);
          if (current && delta && !suppressedInlineFollowUps.current.has(id)) {
            const rawContent = current.content + delta;
            const content = stripInlineFollowUpSection(rawContent);
            if (content !== rawContent) suppressedInlineFollowUps.current.add(id);
            streamMessages.current.set(id, { ...current, content });
            dispatch({ type: 'UPDATE_MESSAGE', payload: { id, patch: { content } } });
          }
          break;
        }
        case 'stream_end': {
          const id = String(message.payload.id || '');
          const current = streamMessages.current.get(id);
          if (current) {
            const content = stripInlineFollowUpSection(current.content);
            streamMessages.current.delete(id);
            suppressedInlineFollowUps.current.delete(id);
            dispatch({ type: 'UPDATE_MESSAGE', payload: { id, patch: { content } } });
          }
          dispatch({ type: 'UPDATE_MESSAGE', payload: { id, patch: { streaming: false } } });
          break;
        }
        case 'search_status': {
          const id = String(message.payload.id || '');
          const current = streamMessages.current.get(id);
          const searchResults = normalizeSearchMeta(message.payload.search_results);
          const skill = {
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
          };
          if (current) {
            streamMessages.current.set(id, {
              ...current,
              skill,
              searchResults: searchResults || current.searchResults,
            });
          }
          dispatch({
            type: 'UPDATE_MESSAGE',
            payload: {
              id,
              patch: {
                skill,
                ...(searchResults ? { searchResults } : {}),
              },
            },
          });
          break;
        }
        case 'follow_ups': {
          const id = String(message.payload.id || '');
          const items = Array.isArray(message.payload.items)
            ? message.payload.items.filter((item): item is string => typeof item === 'string').slice(0, 3)
            : [];
          const current = streamMessages.current.get(id);
          if (current && items.length) {
            streamMessages.current.set(id, { ...current, followUps: items });
          }
          if (items.length) {
            dispatch({ type: 'UPDATE_MESSAGE', payload: { id, patch: { followUps: items } } });
          }
          break;
        }
        case 'travel_plan': {
          const id = String(message.payload.id || '');
          const current = streamMessages.current.get(id);
          const plan = message.payload.plan && typeof message.payload.plan === 'object'
            ? message.payload.plan as Record<string, unknown>
            : {};
          const statusText = plan.tentative_date
            ? `已按 ${String(plan.start_date || '明天')} 暂定写入日程，可在右侧日历修改`
            : '个性化行程已写入右侧日历';
          const skill = {
            intent: 'travel',
            mode: 'immediate',
            content: '',
            icon: '🗺️',
            action_label: '',
            params: {},
            data: { status: 'planned', statusText },
          };
          if (current) streamMessages.current.set(id, { ...current, skill });
          dispatch({ type: 'UPDATE_MESSAGE', payload: { id, patch: { skill } } });
          const schedules = Array.isArray(message.payload.schedules)
            ? message.payload.schedules as ScheduleItem[]
            : [];
          if (schedules.length) {
            // The event is the authoritative write result. Render it
            // immediately instead of depending on a second snapshot request.
            dispatch({ type: 'MERGE_SCHEDULES', payload: schedules });
          }
          const firstStart = Number(schedules[0]?.start_time || 0);
          if (firstStart > 0) {
            const target = new Date(firstStart * 1000);
            const date = [
              target.getFullYear(),
              String(target.getMonth() + 1).padStart(2, '0'),
              String(target.getDate()).padStart(2, '0'),
            ].join('-');
            dispatch({ type: 'PULSE_CALENDAR', payload: { date, count: schedules.length } });
            MessagePlugin.success(`已写入日历：${schedules.length} 项安排`);
          }
          break;
        }
        case 'map_places': {
          const places = Array.isArray(message.payload.places)
            ? message.payload.places as unknown as MakersMapPlace[]
            : [];
          if (places.length) {
            dispatch({
              type: 'SET_MAP_PLACES',
              payload: { places, title: String(message.payload.title || '推荐地点') },
            });
          }
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
        if (!disposed) {
          dispatch({ type: 'HYDRATE_MESSAGES', payload: data.messages });
          if (data.schedules?.length) {
            dispatch({ type: 'MERGE_SCHEDULES', payload: data.schedules });
            const planDate = data.travel_plan?.start_date;
            const firstStart = Number(data.schedules[0]?.start_time || 0);
            const restoredDate = planDate || (firstStart > 0
              ? (() => {
                  const target = new Date(firstStart * 1000);
                  return [
                    target.getFullYear(),
                    String(target.getMonth() + 1).padStart(2, '0'),
                    String(target.getDate()).padStart(2, '0'),
                  ].join('-');
                })()
              : '');
            if (restoredDate) {
              // Refresh restores selection but must never replay the one-shot
              // write animation.
              dispatch({ type: 'FOCUS_CALENDAR', payload: restoredDate });
            }
          }
          const restoredMap = data.messages.slice().reverse().find((item) => item.mapPlaces?.length);
          if (restoredMap?.mapPlaces?.length) {
            dispatch({
              type: 'SET_MAP_PLACES',
              payload: { places: restoredMap.mapPlaces, title: '最近推荐地点' },
            });
          }
        }
      })
      .catch((error) => console.warn('bootstrap failed', error))
      .finally(() => dispatch({ type: 'SET_CONNECTED', payload: true }));

    return () => {
      disposed = true;
      off();
      client.close();
    };
  }, [conversationId, userId, dispatch]);

  return clientRef;
}
