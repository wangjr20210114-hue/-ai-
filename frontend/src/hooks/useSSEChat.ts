import { useEffect, useRef } from 'react';
import { MessagePlugin } from 'tdesign-react';
import { bootstrapApp, proactiveOperation, workspaceOperation } from '../services/api';
import type { BootstrapData, MakersChatRun } from '../services/api';
import { withEdgeOneAuth } from '../services/auth';
import { presentableChatError } from '../services/chatError';
import { durableMessageCount, makersConversationHeaders, mergeMessages, settleStoppedMessages } from '../services/conversation';
import { splitSseFrames } from '../services/sse';
import { useAppDispatch, useAppState } from '../store/appState';
import type { ChatMessage, PaperInfo, ScheduleItem, SearchMeta, WorkspaceAction } from '../types';

type ClientEvent = { type: string; payload: Record<string, unknown> };

export function mergeSearchMeta(previous: SearchMeta | undefined, incoming: Partial<SearchMeta>): SearchMeta {
  const previousMedia = previous?.media || [];
  const incomingMedia = Array.isArray(incoming.media) ? incoming.media : [];
  const previousImages = previous?.images || [];
  const incomingImages = Array.isArray(incoming.images) ? incoming.images : [];
  const retainedMedia = incomingMedia.length ? incomingMedia : previousMedia;
  const retainedImages = incomingImages.length ? incomingImages : previousImages;
  return {
    ...(previous || {}),
    ...incoming,
    query: String(incoming.query ?? previous?.query ?? ''),
    results: Array.isArray(incoming.results) ? incoming.results : (previous?.results || []),
    media: retainedMedia,
    images: retainedImages,
    sources_used: Array.isArray(incoming.sources_used) ? incoming.sources_used : (previous?.sources_used || []),
    total: typeof incoming.total === 'number' ? incoming.total : (previous?.total || 0),
    media_pending: previous?.media_pending === false && previousMedia.length > 0
      ? false
      : (incoming.media_pending ?? previous?.media_pending),
  };
}

export function shouldPublishProactiveOpening(restored: ChatMessage[], latest: ChatMessage[]): boolean {
  return durableMessageCount(restored) === 0 && durableMessageCount(latest) === 0;
}

function responseError(data: unknown, fallback: string): string {
  if (Array.isArray(data) && data[0] && typeof data[0] === 'object') {
    return responseError(data[0], fallback);
  }
  if (data && typeof data === 'object') {
    const value = data as { error?: unknown; detail?: unknown; message?: unknown };
    return String(value.error || value.detail || value.message || fallback);
  }
  return fallback;
}

class SSEChatClient {
  private controller: AbortController | null = null;
  private resumeController: AbortController | null = null;
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
    this.resumeController?.abort();
    this.resumeController = null;
    // Settle the UI immediately for both a live response stream and a
    // checkpoint-resume stream. Makers cancellation remains the durable
    // backend operation, but it must not leave the composer locked while the
    // platform propagates the abort.
    this.emit({ type: 'stop_requested', payload: {} });
    try {
      const response = await fetch(withEdgeOneAuth('/stop'), {
        method: 'POST',
        // Makers documents that stop must not carry the target conversation
        // header, otherwise this request can replace the active run signal.
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ conversation_id: this.conversationId }),
        credentials: 'same-origin',
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const stopResult = await response.json() as { run_id?: string | null };
      const stoppedRunId = String(stopResult.run_id || '');
      // The platform acknowledges cancel_requested before the detached
      // producer necessarily reaches its next cancellation checkpoint. Keep
      // the composer gated until Makers publishes a terminal run state, so a
      // quick follow-up is never rejected as "still processing".
      for (let attempt = 0; attempt < 30; attempt += 1) {
        const run = (await bootstrapApp(this.conversationId)).run;
        const sameRun = !stoppedRunId || String(run?.run_id || '') === stoppedRunId;
        if (run && sameRun && ['cancelled', 'completed', 'failed'].includes(String(run.status || ''))) return;
        await new Promise((resolve) => window.setTimeout(resolve, 500));
      }
      throw new Error('取消已提交，但运行尚未结束');
    } catch {
      // Best-effort cancellation; the aborted request signal and Makers
      // cancel_requested marker remain the first lines of defence.
      throw new Error('停止请求未确认，请稍后重试');
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

    const clientMessage = message.payload?.client_message;
    if (clientMessage && typeof clientMessage === 'object') {
      this.emit({ type: 'optimistic_user', payload: { message: clientMessage } });
    }

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
          detail = responseError(await response.json(), detail);
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
              case 'ai_response_reset':
                this.emit({ type: 'stream_reset', payload: { id: streamId } });
                break;
              case 'tool_call':
                {
                  const toolName = String(event.name || '');
                  // Some provider streams include a companion tool-call chunk
                  // without a name. It is transport noise, not a new search.
                  if (!toolName) break;
                  const labels: Record<string, string> = {
                    web_search: '正在查找相关信息…',
                    search_places: '正在核实真实地点…',
                    prepare_map_recommendation: '正在准备可查看的地图地点…',
                    propose_calendar_changes: '正在整理待确认的日程变更…',
                    propose_meeting: '正在准备会议创建信息…',
                    propose_image: '正在直接生成图片…',
                    image_generation_planning: '正在准备绘制画面…',
                    rich_search: '正在查找可靠的事实与视觉参考…',
                    search_arxiv: '正在搜索 arXiv 论文…',
                    collect_page_images: '正在提取网页图片…',
                    search_rich_images: '正在查找相关图片…',
                    analyze_images_parallel: '正在并行识别图片…',
                  };
                this.emit({
                  type: 'search_status',
                  payload: {
                    id: streamId,
                    status: 'searching',
                    statusText: labels[toolName] || '正在处理…',
                    intent: ['image_generation_planning', 'propose_image'].includes(toolName) ? 'image' : '',
                  },
                });
                }
                break;
              case 'tool_result':
                if (!String(event.name || '')) break;
                this.emit({
                  type: 'search_status',
                  payload: { id: streamId, status: 'analyzing', statusText: '工具已返回，正在整理…' },
                });
                break;
              case 'map_action':
              case 'calendar_action':
              case 'side_effect_action':
                this.emit({
                  type: String(event.type),
                  payload: {
                    ...((event.payload && typeof event.payload === 'object') ? event.payload as Record<string, unknown> : {}),
                    id: streamId,
                  },
                });
                break;
              case 'search_results':
                this.emit({
                  type: 'search_results',
                  payload: {
                    ...((event.payload && typeof event.payload === 'object') ? event.payload as Record<string, unknown> : {}),
                    id: streamId,
                  },
                });
                break;
              case 'search_media':
                this.emit({
                  type: 'search_media',
                  payload: {
                    ...((event.payload && typeof event.payload === 'object') ? event.payload as Record<string, unknown> : {}),
                    id: streamId,
                  },
                });
                break;
              case 'paper_results':
                this.emit({
                  type: 'paper_results',
                  payload: {
                    ...((event.payload && typeof event.payload === 'object') ? event.payload as Record<string, unknown> : {}),
                    id: streamId,
                  },
                });
                break;
              case 'follow_ups':
                {
                const followUpPayload = event.payload && typeof event.payload === 'object'
                  ? event.payload as Record<string, unknown>
                  : {};
                this.emit({
                  type: 'follow_ups',
                  payload: {
                    id: streamId,
                    items: Array.isArray(followUpPayload.items) ? followUpPayload.items : [],
                  },
                });
                break;
                }
              case 'error_message':
                this.emit({
                  type: 'error',
                  payload: { id: streamId, message: typeof event.content === 'string' ? event.content : '服务异常' },
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
          payload: { id: streamId, message: (error as Error).message || '请求失败' },
        });
      }
      finish();
    } finally {
      if (this.controller?.signal === signal) this.controller = null;
    }
  }

  async resume(): Promise<void> {
    this.resumeController?.abort();
    const controller = new AbortController();
    this.resumeController = controller;
    const streamId = `ai-resume-${Date.now()}`;
    this.emit({ type: 'stream_start', payload: { id: streamId, intent: 'chat', resumed: true } });
    try {
      for (let attempt = 0; attempt < 240 && !controller.signal.aborted; attempt += 1) {
        const data = await bootstrapApp(this.conversationId);
        if (controller.signal.aborted) throw new DOMException('Aborted', 'AbortError');
        const run = data.run;
        this.emit({ type: 'checkpoint_snapshot', payload: { id: streamId, data } });
        const lastMessage = data.messages[data.messages.length - 1];
        const hasFinalAnswer = lastMessage?.role === 'ai' && Boolean(lastMessage.content.trim());
        if (run?.status === 'cancelled') {
          this.emit({ type: 'stream_end', payload: { id: streamId } });
          return;
        }
        if (run?.status === 'completed' && hasFinalAnswer) {
          this.emit({ type: 'stream_end', payload: { id: streamId } });
          return;
        }
        if (!run?.status && hasFinalAnswer) {
          this.emit({ type: 'stream_end', payload: { id: streamId } });
          return;
        }
        if (run?.status === 'failed') {
          this.emit({ type: 'error', payload: { id: streamId, message: run.error || '处理失败，请重试' } });
          return;
        }
        await new Promise<void>((resolve, reject) => {
          const timer = window.setTimeout(resolve, 1500);
          controller.signal.addEventListener('abort', () => {
            window.clearTimeout(timer);
            reject(new DOMException('Aborted', 'AbortError'));
          }, { once: true });
        });
      }
    } catch (error) {
      if ((error as Error).name !== 'AbortError') {
        this.emit({ type: 'error', payload: { id: streamId, message: (error as Error).message || '恢复运行失败' } });
      }
    } finally {
      if (this.resumeController === controller) this.resumeController = null;
    }
  }

  close() {
    // Unmount/refresh only detaches this page. Explicit user cancellation is
    // handled by stop(); never turn a browser refresh into a server-side stop.
    this.controller?.abort();
    this.controller = null;
    this.resumeController?.abort();
    this.resumeController = null;
  }
}

const MESSAGE_CACHE_PREFIX = 'yuanbao.messages.';

function readMessageCache(conversationId: string): ChatMessage[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(`${MESSAGE_CACHE_PREFIX}${conversationId}`) || '[]') as ChatMessage[];
    return Array.isArray(parsed)
      ? parsed.filter((item) => !item.failed && (item.role === 'user' || item.content.trim())).map((item) => ({ ...item, streaming: false }))
      : [];
  } catch { return []; }
}

function writeMessageCache(conversationId: string, messages: ChatMessage[]) {
  const durable = messages.filter((item) => !item.failed && (item.role === 'user' || item.content.trim()));
  try { localStorage.setItem(`${MESSAGE_CACHE_PREFIX}${conversationId}`, JSON.stringify(durable.slice(-60))); }
  catch { /* Remote checkpoints remain the durable fallback. */ }
}

export function useSSEChat() {
  const { conversationId, messages, conversations } = useAppState();
  const dispatch = useAppDispatch();
  const clientRef = useRef<SSEChatClient | null>(null);
  const clientsRef = useRef(new Map<string, { client: SSEChatClient; off: () => void }>());
  const cacheRef = useRef(new Map<string, ChatMessage[]>());
  const streamsRef = useRef(new Map<string, Map<string, ChatMessage>>());
  const activeConversationRef = useRef(conversationId);
  const conversationsRef = useRef(conversations);
  activeConversationRef.current = conversationId;
  conversationsRef.current = conversations;

  const setConversationActivity = (id: string, activityStatus: 'idle' | 'running' | 'failed') => {
    const now = Date.now();
    const previous = conversationsRef.current.find((item) => item.id === id);
    const messageCount = durableMessageCount(cached(id));
    const next = {
      id,
      title: previous?.title || '新对话',
      createdAt: previous?.createdAt || now,
      updatedAt: now,
      messageCount: Math.max(Number(previous?.messageCount || 0), messageCount),
      pending: activityStatus === 'running' ? previous?.pending : false,
      activityStatus,
    };
    conversationsRef.current = [next, ...conversationsRef.current.filter((item) => item.id !== id)];
    dispatch({ type: 'UPSERT_CONVERSATION', payload: next });
  };

  const publish = (id: string, next: ChatMessage[]) => {
    cacheRef.current.set(id, next);
    writeMessageCache(id, next);
    if (activeConversationRef.current === id) dispatch({ type: 'HYDRATE_MESSAGES', payload: next });
  };
  const cached = (id: string) => {
    if (!cacheRef.current.has(id)) cacheRef.current.set(id, readMessageCache(id));
    return cacheRef.current.get(id) || [];
  };
  const patch = (id: string, messageId: string, messagePatch: Partial<ChatMessage>, delta = '') => {
    publish(id, cached(id).map((item) => item.id === messageId
      ? { ...item, ...messagePatch, content: delta ? item.content + delta : (messagePatch.content ?? item.content) }
      : item));
  };

  const ensureClient = (id: string) => {
    const existing = clientsRef.current.get(id);
    if (existing) return existing.client;
    const client = new SSEChatClient(id);
    const streams = new Map<string, ChatMessage>();
    streamsRef.current.set(id, streams);
    const off = client.on((event) => {
      const streamId = String(event.payload.id || '');
      switch (event.type) {
        case 'optimistic_user': {
          const message = event.payload.message as ChatMessage | undefined;
          if (!message?.id || message.role !== 'user') break;
          const current = cached(id);
          publish(id, current.some((item) => item.id === message.id) ? current : [...current, message]);
          break;
        }
        case 'stream_start': {
          const streamMessage: ChatMessage = {
            id: streamId || `ai-stream-${Date.now()}`, role: 'ai', content: '', ts: Date.now(), streaming: true,
            skill: { intent: 'chat', mode: 'immediate', content: '', icon: '✨', action_label: '', params: {}, data: { status: 'thinking', statusText: '思考中…' } },
          };
          streams.set(streamMessage.id, streamMessage);
          const current = cached(id).filter((item) => item.id !== streamMessage.id && !item.failed);
          publish(id, [...current, streamMessage]);
          setConversationActivity(id, 'running');
          break;
        }
        case 'stream_delta': {
          const current = streams.get(streamId); const delta = String(event.payload.delta || '');
          if (current && delta) { const next = { ...current, content: current.content + delta }; streams.set(streamId, next); patch(id, streamId, {}, delta); }
          break;
        }
        case 'checkpoint_snapshot': {
          const current = streams.get(streamId);
          const data = event.payload.data as BootstrapData | undefined;
          if (!current || !data || !Array.isArray(data.messages)) break;
          const run = data.run as MakersChatRun | null | undefined;
          const merged = mergeMessages(data.messages, cached(id));
          const lastMessage = data.messages[data.messages.length - 1];
          const hasFinalAnswer = lastMessage?.role === 'ai' && Boolean(lastMessage.content.trim());
          const keepPlaceholder = !hasFinalAnswer && run?.status !== 'cancelled';
          publish(id, keepPlaceholder ? [...merged, current] : merged);
          if (activeConversationRef.current === id) {
            dispatch({ type: 'HYDRATE_WORKSPACE', payload: { schedules: data.schedules, mapPlaces: data.map_places, mapTitle: data.map_title } });
          }
          break;
        }
        case 'stream_reset': {
          const current = streams.get(streamId);
          if (current) {
            const next = { ...current, content: '' };
            streams.set(streamId, next); patch(id, streamId, { content: '' });
          }
          break;
        }
        case 'stream_end': {
          const current = streams.get(streamId);
          if (current) {
            streams.delete(streamId);
            if (current.failed) break;
            if (!current.content.trim()) {
              publish(id, cached(id).filter((item) => item.id !== streamId));
              setConversationActivity(id, 'idle');
              break;
            }
            const complete = { ...current, streaming: false };
            patch(id, streamId, complete);
            setConversationActivity(id, 'idle');
          }
          break;
        }
        case 'stop_requested': {
          streams.clear();
          publish(id, settleStoppedMessages(cached(id)));
          setConversationActivity(id, 'idle');
          break;
        }
        case 'search_status': {
          const current = streams.get(streamId); if (!current) break;
          const intent = event.payload.intent === 'image' || current.skill?.intent === 'image' ? 'image' : 'search';
          const skill = { intent, mode: 'immediate', content: '', icon: intent === 'image' ? '🎨' : '🔍', action_label: '', params: {}, data: { status: String(event.payload.status || 'searching'), statusText: String(event.payload.statusText || '正在搜索…') } } as ChatMessage['skill'];
          streams.set(streamId, { ...current, skill }); patch(id, streamId, { skill }); break;
        }
        case 'search_results': {
          const current = streams.get(streamId); const incoming = event.payload as unknown as Partial<SearchMeta>;
          if (current && Array.isArray(incoming.results)) {
            const searchResults = mergeSearchMeta(current.searchResults, incoming);
            streams.set(streamId, { ...current, searchResults }); patch(id, streamId, { searchResults });
          }
          break;
        }
        case 'search_media': {
          const current = streams.get(streamId); if (!current) break;
          const searchResults = mergeSearchMeta(current.searchResults, {
            query: String(event.payload.query || ''),
            media: Array.isArray(event.payload.media) ? event.payload.media : [],
            images: Array.isArray(event.payload.images) ? event.payload.images : [],
            media_pending: false,
            vision_diagnostics: event.payload.vision_diagnostics as Record<string, number> | undefined,
            timings_ms: event.payload.timings_ms as Record<string, number> | undefined,
          } as Partial<SearchMeta>);
          streams.set(streamId, { ...current, searchResults }); patch(id, streamId, { searchResults });
          break;
        }
        case 'paper_results': {
          const current = streams.get(streamId); const papers = Array.isArray(event.payload.papers) ? event.payload.papers as PaperInfo[] : [];
          if (current && papers.length) { streams.set(streamId, { ...current, papers }); patch(id, streamId, { papers }); }
          break;
        }
        case 'follow_ups': {
          const current = streams.get(streamId);
          const followUps = Array.isArray(event.payload.items)
            ? event.payload.items.map(String).filter(Boolean).slice(0, 3)
            : [];
          if (current && followUps.length) {
            const next = { ...current, followUps };
            streams.set(streamId, next); patch(id, streamId, { followUps });
          }
          break;
        }
        case 'map_action': case 'calendar_action': case 'side_effect_action': {
          const current = streams.get(streamId); const action = event.payload.action as WorkspaceAction | undefined;
          if (current && action?.id) {
            const workspaceActions = [...(current.workspaceActions || []).filter((item) => item.id !== action.id), action];
            streams.set(streamId, { ...current, workspaceActions }); patch(id, streamId, { workspaceActions });
            if (event.type === 'map_action' && action.kind === 'map_recommendation' && action.status === 'ready') {
              void workspaceOperation(id, 'activate_map', { action_id: action.id, version: action.version })
                .then((response) => {
                  if (response.map?.places?.length) {
                    dispatch({ type: 'SET_MAP_PLACES', payload: { places: response.map.places, title: response.map.title } });
                  }
                  const activated = response.action;
                  const latest = streams.get(streamId);
                  if (latest && activated) {
                    const nextActions = [...(latest.workspaceActions || []).filter((item) => item.id !== activated.id), activated];
                    streams.set(streamId, { ...latest, workspaceActions: nextActions });
                    patch(id, streamId, { workspaceActions: nextActions });
                  }
                })
                .catch((error) => console.warn('automatic map activation failed', error));
            }
          }
          break;
        }
        case 'error': {
          const message = presentableChatError(event.payload.message);
          const current = streams.get(streamId);
          if (current) {
            const next = {
              ...current,
              content: message,
              streaming: false,
              failed: true,
              skill: current.skill ? {
                ...current.skill,
                data: { ...current.skill.data, status: 'error', statusText: '处理失败' },
              } : current.skill,
            };
            streams.set(streamId, next);
            patch(id, streamId, { content: message, streaming: false, failed: true, skill: next.skill });
          }
          setConversationActivity(id, 'failed');
          if (activeConversationRef.current === id) MessagePlugin.error(message);
          break;
        }
      }
    });
    clientsRef.current.set(id, { client, off });
    return client;
  };

  useEffect(() => {
    // Capture user messages and local UI changes before switching away.
    const existing = cached(conversationId);
    if (messages.length || !existing.length) publish(conversationId, messages);
    // publish is intentionally bound to the current active-conversation ref.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId, messages]);

  useEffect(() => {
    let disposed = false;
    const client = ensureClient(conversationId);
    clientRef.current = client;
    const local = cached(conversationId);
    dispatch({ type: 'HYDRATE_MESSAGES', payload: local });
    void bootstrapApp(conversationId).then((data) => {
      if (disposed) return;
      const merged = mergeMessages(data.messages, cached(conversationId));
      publish(conversationId, merged);
      const summary = conversationsRef.current.find((item) => item.id === conversationId);
      if (summary && summary.messageCount !== merged.length) {
        const reconciled = { ...summary, messageCount: merged.length };
        conversationsRef.current = conversationsRef.current.map((item) => (
          item.id === conversationId ? reconciled : item
        ));
        dispatch({ type: 'UPSERT_CONVERSATION', payload: reconciled });
      }
      if (activeConversationRef.current === conversationId) {
        dispatch({ type: 'HYDRATE_WORKSPACE', payload: { schedules: data.schedules, mapPlaces: data.map_places, mapTitle: data.map_title } });
        void proactiveOperation(conversationId, merged.length === 0 ? 'open_conversation' : 'refresh').then((proactive) => {
          if (!disposed && activeConversationRef.current === conversationId) {
            dispatch({ type: 'HYDRATE_PROACTIVE', payload: proactive });
            const opening = proactive.proactive_message;
            if (merged.length === 0 && opening?.content) {
              const latest = cached(conversationId);
              if (shouldPublishProactiveOpening(merged, latest)) {
                publish(conversationId, [opening]);
              }
            }
          }
        }).catch((error) => console.warn('proactive bootstrap failed', error));
        dispatch({ type: 'SET_CONNECTED', payload: true });
      }
      const latestSummary = conversationsRef.current.find((item) => item.id === conversationId);
      const hasUnansweredUser = merged.length > 0 && merged[merged.length - 1]?.role === 'user';
      if (latestSummary?.activityStatus === 'running' || hasUnansweredUser) {
        void client.resume();
      }
    }).catch((error) => console.warn('bootstrap failed', error));
    return () => { disposed = true; };
    // Clients are retained by id so background conversations keep running.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  useEffect(() => () => {
    clientsRef.current.forEach(({ client, off }) => { off(); client.close(); });
    clientsRef.current.clear();
  }, []);

  useEffect(() => {
    const refreshWorkspace = (event: Event) => {
      const detail = (event as CustomEvent<{ schedules?: unknown }>).detail;
      if (Array.isArray(detail?.schedules)) {
        dispatch({ type: 'SET_SCHEDULES', payload: detail.schedules as ScheduleItem[] });
      }
    };
    const refreshProactive = () => {
      void proactiveOperation(activeConversationRef.current, 'refresh')
        .then((proactive) => dispatch({ type: 'HYDRATE_PROACTIVE', payload: proactive }))
        .catch((error) => console.warn('proactive workspace refresh failed', error));
    };
    window.addEventListener('yuanbao:workspace-changed', refreshWorkspace);
    window.addEventListener('yuanbao:calendar-changed', refreshProactive);
    return () => {
      window.removeEventListener('yuanbao:workspace-changed', refreshWorkspace);
      window.removeEventListener('yuanbao:calendar-changed', refreshProactive);
    };
  }, [dispatch]);

  return clientRef;
}
