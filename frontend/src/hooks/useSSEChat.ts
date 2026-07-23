import { useEffect, useRef } from 'react';
import { MessagePlugin } from 'tdesign-react';
import { bootstrapApp, proactiveOperation } from '../services/api';
import type { BootstrapData, MakersChatRun } from '../services/api';
import { withEdgeOneAuth } from '../services/auth';
import { presentableChatError } from '../services/chatError';
import { durableMessageCount, makersConversationHeaders, mergeMessages, normalizeMessages, reconcileCompletedMessage, settleStoppedMessages } from '../services/conversation';
import { splitSseFrames } from '../services/sse';
import { useAppDispatch, useAppState } from '../store/appState';
import type { ChatMessage, ClarificationPrompt, PaperInfo, ProactiveState, ScheduleItem, SearchMeta, WorkspaceAction } from '../types';

type ClientEvent = { type: string; payload: Record<string, unknown> };

const STREAM_IDLE_TIMEOUT_MS = 20_000;
const RECOVERY_DEADLINE_MS = 120_000;
const STOP_TIMEOUT_MS = 4_000;

export function isRecoverableTransportError(error: unknown): boolean {
  const value = error as { name?: unknown; message?: unknown };
  if (String(value?.name || '') === 'AbortError') return false;
  const message = String(value?.message || error || '').toLowerCase();
  return (
    String(value?.name || '') === 'TypeError'
    || /failed to fetch|network|load failed|connection|fetch failed|network request failed/.test(message)
  );
}

function waitWithAbort(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(resolve, milliseconds);
    signal.addEventListener('abort', () => {
      window.clearTimeout(timer);
      reject(new DOMException('Aborted', 'AbortError'));
    }, { once: true });
  });
}

const TOOL_PROGRESS: Record<string, { active: string; complete: string }> = {
  web_search: { active: '正在查找可核验的信息…', complete: '已找到相关资料，正在核对时间和出处…' },
  rich_search: { active: '正在查找最新且可靠的资料与图片…', complete: '资料已经找到，正在核对重点、日期和出处…' },
  search_places: { active: '正在查找并确认真实地点…', complete: '地点已经找到，正在确认名称和位置…' },
  prepare_map_recommendation: { active: '正在把核实过的地点整理到地图…', complete: '地图地点已准备好，正在组织推荐理由…' },
  recommend_places_on_map: { active: '正在逐个核实地点并准备地图…', complete: '可用地点已核实，正在整理成推荐…' },
  propose_calendar_changes: { active: '正在检查时间、地点和日程冲突…', complete: '日程条件已检查，正在准备确认内容…' },
  propose_meeting: { active: '正在检查会议时间和必要信息…', complete: '会议信息已检查，正在准备确认内容…' },
  propose_image: { active: '正在理解画面并开始绘制…', complete: '画面已生成，正在整理展示结果…' },
  image_generation_planning: { active: '正在理解画面主体、风格和构图…', complete: '画面要求已整理，正在开始绘制…' },
  search_arxiv: { active: '正在查找论文并核对作者与年份…', complete: '论文已找到，正在核对摘要和下载信息…' },
  collect_page_images: { active: '正在查看网页里真正有用的图片…', complete: '网页图片已提取，正在筛选与问题相关的内容…' },
  search_rich_images: { active: '正在查找与问题相关的图片…', complete: '候选图片已找到，正在确认是否真的相关…' },
  analyze_images_parallel: { active: '正在逐张确认图片内容和相关性…', complete: '图片内容已确认，正在放到合适的位置…' },
};

export function progressTextForTool(toolName: string, phase: 'active' | 'complete'): string {
  return TOOL_PROGRESS[toolName]?.[phase]
    || (phase === 'active' ? '正在处理这一步需要的信息…' : '这一步已完成，正在整理结果…');
}

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

export function actionOnlyFallback(actions: WorkspaceAction[] | undefined): string {
  const kinds = new Set((actions || []).map((action) => action.kind));
  if (kinds.has('map_recommendation')) return '地点已经核实，请点击下方按钮显示地点。';
  if (kinds.has('meeting_create')) return '腾讯会议确认卡已准备好，请补齐并核对条件。';
  if (kinds.has('calendar_changes')) return '日程变更确认卡已准备好，请核对后确认。';
  if (kinds.has('image_generate')) return '图片任务已准备好，可在下方查看结果。';
  return '';
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

  hasActiveTransport(): boolean {
    return Boolean(this.controller || this.resumeController);
  }

  async stop(): Promise<'confirmed' | 'local'> {
    this.controller?.abort();
    this.controller = null;
    this.resumeController?.abort();
    this.resumeController = null;
    // Settle the UI immediately for both a live response stream and a
    // checkpoint-resume stream. Makers cancellation remains the durable
    // backend operation, but it must not leave the composer locked while the
    // platform propagates the abort.
    this.emit({ type: 'stop_requested', payload: {} });
    const stopController = new AbortController();
    const stopTimer = window.setTimeout(() => stopController.abort(), STOP_TIMEOUT_MS);
    const requestStop = () => fetch(withEdgeOneAuth('/stop'), {
      method: 'POST',
      // Makers documents that stop must not carry the target conversation
      // header, otherwise this request can replace the active run signal.
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: this.conversationId }),
      credentials: 'same-origin',
      signal: stopController.signal,
    });
    try {
      const response = await requestStop();
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return 'confirmed';
    } catch {
      // The browser must be usable immediately even while offline. Retry the
      // same Makers cancellation once the network comes back; no local queue
      // or duplicate Agent run is created.
      window.addEventListener('online', () => {
        void fetch(withEdgeOneAuth('/stop'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ conversation_id: this.conversationId }),
          credentials: 'same-origin',
        }).catch(() => {});
      }, { once: true });
      return 'local';
    } finally {
      window.clearTimeout(stopTimer);
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
    let recoverTransport = false;
    let protocolDone = false;
    let idleWatchdog: number | undefined;
    let watchdogTriggered = false;
    const armWatchdog = () => {
      if (idleWatchdog) window.clearTimeout(idleWatchdog);
      idleWatchdog = window.setTimeout(() => {
        watchdogTriggered = true;
        this.controller?.abort();
      }, STREAM_IDLE_TIMEOUT_MS);
    };

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
      armWatchdog();
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
      armWatchdog();

      const reader = response.body?.getReader();
      if (!reader) throw new Error('无法读取响应流');

      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        armWatchdog();
        buffer += decoder.decode(value, { stream: true });
        const parsed = splitSseFrames(buffer);
        buffer = parsed.rest;

        for (const frame of parsed.frames) {
          if (frame === '[DONE]') {
            protocolDone = true;
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
                this.emit({
                  type: 'search_status',
                  payload: {
                    id: streamId,
                    status: 'searching',
                    statusText: progressTextForTool(toolName, 'active'),
                    intent: ['image_generation_planning', 'propose_image'].includes(toolName) ? 'image' : '',
                  },
                });
                }
                break;
              case 'tool_result':
                if (!String(event.name || '')) break;
                this.emit({
                  type: 'search_status',
                  payload: {
                    id: streamId,
                    status: 'analyzing',
                    statusText: progressTextForTool(String(event.name || ''), 'complete'),
                  },
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
              case 'clarification_action':
                this.emit({
                  type: 'clarification_action',
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
                  type: 'search_status',
                  payload: { id: streamId, status: 'arranging', statusText: '相关图片已经核对，正在放到合适的段落…' },
                });
                this.emit({
                  type: 'search_media',
                  payload: {
                    ...((event.payload && typeof event.payload === 'object') ? event.payload as Record<string, unknown> : {}),
                    id: streamId,
                  },
                });
                break;
              case 'answer_complete':
                this.emit({ type: 'answer_complete', payload: { id: streamId } });
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
              case 'proactive_update':
                this.emit({
                  type: 'proactive_update',
                  payload: (event.payload && typeof event.payload === 'object')
                    ? event.payload as Record<string, unknown>
                    : {},
                });
                break;
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
      // The Agent protocol always closes with [DONE]. A bare EOF usually
      // means the network path disappeared without surfacing a fetch error.
      if (!protocolDone) recoverTransport = true;
      else finish();
    } catch (error) {
      recoverTransport = watchdogTriggered || isRecoverableTransportError(error);
      if (!recoverTransport && (error as Error).name !== 'AbortError') {
        this.emit({
          type: 'error',
          payload: { id: streamId, message: (error as Error).message || '请求失败' },
        });
      }
      if (!recoverTransport) finish();
    } finally {
      if (idleWatchdog) window.clearTimeout(idleWatchdog);
      if (this.controller?.signal === signal) this.controller = null;
    }
    if (recoverTransport) {
      this.emit({
        type: 'transport_recovering',
        payload: { id: streamId, message: '网络有波动，正在从 Makers 已保存的进度恢复…' },
      });
      await this.resume(streamId, true);
    }
  }

  async resume(existingStreamId?: string, recovering = false): Promise<void> {
    // Switching conversations must not replace a still-live response with a
    // polling snapshot. The original request keeps publishing into its
    // conversation cache while it is in the background.
    if (this.controller || this.resumeController) return;
    const controller = new AbortController();
    this.resumeController = controller;
    const streamId = existingStreamId || `ai-resume-${Date.now()}`;
    if (!recovering) {
      this.emit({ type: 'stream_start', payload: { id: streamId, intent: 'chat', resumed: true } });
    }
    const deadline = Date.now() + RECOVERY_DEADLINE_MS;
    let lastError: unknown;
    try {
      while (Date.now() < deadline && !controller.signal.aborted) {
        let data: BootstrapData;
        try {
          data = await bootstrapApp(this.conversationId, {
            signal: controller.signal,
            strict: true,
            timeoutMs: 4000,
          });
          lastError = undefined;
        } catch (error) {
          if ((error as Error).name === 'AbortError' && controller.signal.aborted) throw error;
          lastError = error;
          await waitWithAbort(1500, controller.signal);
          continue;
        }
        if (controller.signal.aborted) throw new DOMException('Aborted', 'AbortError');
        const run = data.run;
        this.emit({ type: 'checkpoint_snapshot', payload: { id: streamId, data } });
        const lastMessage = data.messages[data.messages.length - 1];
        const hasFinalAnswer = lastMessage?.role === 'ai' && Boolean(lastMessage.content.trim());
        if (run?.status === 'cancelled') {
          this.emit({ type: 'checkpoint_complete', payload: { id: streamId } });
          return;
        }
        if (run?.status === 'completed' && hasFinalAnswer) {
          this.emit({ type: 'checkpoint_complete', payload: { id: streamId } });
          return;
        }
        if (!run?.status && hasFinalAnswer) {
          this.emit({ type: 'checkpoint_complete', payload: { id: streamId } });
          return;
        }
        if (run?.status === 'failed') {
          this.emit({ type: 'error', payload: { id: streamId, message: run.error || '处理失败，请重试' } });
          return;
        }
        await waitWithAbort(1500, controller.signal);
      }
      if (!controller.signal.aborted) {
        this.emit({
          type: 'transport_failed',
          payload: {
            id: streamId,
            message: lastError
              ? '网络中断后暂时无法读取 Makers 进度，本轮已结束等待。网络恢复后可重新进入对话核对结果。'
              : '两分钟内仍未取得最终结果，本轮已结束等待。你可以重新发送，稍后也可回到对话核对结果。',
          },
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
    const normalized = normalizeMessages(next);
    cacheRef.current.set(id, normalized);
    writeMessageCache(id, normalized);
    if (activeConversationRef.current === id) dispatch({ type: 'HYDRATE_MESSAGES', payload: normalized });
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
            skill: { intent: 'chat', mode: 'immediate', content: '', icon: '✨', action_label: '', params: {}, data: { status: 'thinking', statusText: '正在理解你想解决的问题…' } },
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
          const runActive = run?.status === 'running' || run?.status === 'cancel_requested';
          const merged = mergeMessages(data.messages, cached(id), { preserveStreaming: runActive });
          const lastMessage = data.messages[data.messages.length - 1];
          const hasFinalAnswer = lastMessage?.role === 'ai' && Boolean(lastMessage.content.trim());
          const keepPlaceholder = !hasFinalAnswer && run?.status !== 'cancelled';
          publish(id, keepPlaceholder && !merged.some((item) => item.id === current.id)
            ? [...merged, current]
            : merged);
          if (activeConversationRef.current === id) {
            dispatch({ type: 'HYDRATE_WORKSPACE', payload: { schedules: data.schedules, mapPlaces: data.map_places, mapTitle: data.map_title } });
          }
          break;
        }
        case 'checkpoint_complete': {
          streams.delete(streamId);
          publish(id, cached(id).map((item) => (
            item.streaming ? { ...item, streaming: false } : item
          )));
          setConversationActivity(id, 'idle');
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
            if (!current.content.trim() && !current.workspaceActions?.length && !current.clarification) {
              publish(id, cached(id).filter((item) => item.id !== streamId));
              setConversationActivity(id, 'idle');
              break;
            }
            const complete = {
              ...current,
              content: current.content.trim() ? current.content : actionOnlyFallback(current.workspaceActions),
              streaming: false,
            };
            publish(id, reconcileCompletedMessage(cached(id), complete));
            setConversationActivity(id, 'idle');
          }
          break;
        }
        case 'answer_complete': {
          const current = streams.get(streamId);
          if (current) {
            const next = { ...current, streaming: false };
            streams.set(streamId, next);
            patch(id, streamId, { streaming: false });
          }
          break;
        }
        case 'stop_requested': {
          streams.clear();
          publish(id, settleStoppedMessages(cached(id)));
          setConversationActivity(id, 'idle');
          break;
        }
        case 'transport_recovering': {
          const current = streams.get(streamId);
          if (!current) break;
          const skill = {
            ...(current.skill || {
              intent: 'chat', mode: 'immediate', content: '', icon: '✨',
              action_label: '', params: {}, data: {},
            }),
            data: {
              ...(current.skill?.data || {}),
              status: 'recovering',
              statusText: String(event.payload.message || '网络有波动，正在从已保存进度恢复…'),
            },
          } as ChatMessage['skill'];
          streams.set(streamId, { ...current, skill });
          patch(id, streamId, { skill });
          break;
        }
        case 'transport_failed': {
          const message = String(event.payload.message || '网络恢复超时，本轮已结束等待。');
          const current = streams.get(streamId);
          if (current) {
            const content = current.content.trim() || message;
            const skill = current.skill ? {
              ...current.skill,
              data: { ...current.skill.data, status: 'error', statusText: '连接恢复超时' },
            } : current.skill;
            streams.delete(streamId);
            patch(id, streamId, { content, streaming: false, failed: true, skill });
          }
          setConversationActivity(id, 'failed');
          if (activeConversationRef.current === id) MessagePlugin.warning(message);
          break;
        }
        case 'search_status': {
          const current = streams.get(streamId); if (!current) break;
          const intent = event.payload.intent === 'image' || current.skill?.intent === 'image' ? 'image' : 'search';
          const skill = { intent, mode: 'immediate', content: '', icon: intent === 'image' ? '🎨' : '🔍', action_label: '', params: {}, data: { status: String(event.payload.status || 'searching'), statusText: String(event.payload.statusText || '正在处理需要的信息…') } } as ChatMessage['skill'];
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
        case 'proactive_update': {
          if (activeConversationRef.current === id) {
            dispatch({ type: 'HYDRATE_PROACTIVE', payload: event.payload as unknown as ProactiveState });
          }
          break;
        }
        case 'map_action': case 'calendar_action': case 'side_effect_action': {
          const current = streams.get(streamId); const action = event.payload.action as WorkspaceAction | undefined;
          if (current && action?.id) {
            const workspaceActions = [...(current.workspaceActions || []).filter((item) => item.id !== action.id), action];
            streams.set(streamId, { ...current, workspaceActions }); patch(id, streamId, { workspaceActions });
          }
          break;
        }
        case 'clarification_action': {
          const current = streams.get(streamId);
          const clarification = event.payload.clarification as ClarificationPrompt | undefined;
          if (current && clarification?.id && Array.isArray(clarification.fields) && clarification.fields.length) {
            const next = { ...current, clarification };
            streams.set(streamId, next);
            patch(id, streamId, { clarification });
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
      const runActive = data.run?.status === 'running' || data.run?.status === 'cancel_requested';
      const merged = mergeMessages(data.messages, cached(conversationId), { preserveStreaming: runActive });
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
        // Refresh the durable inbox without injecting a synthetic assistant
        // message into a blank conversation. Header owns the non-blocking
        // presentation so opening a chat cannot race the first user message.
        void proactiveOperation(conversationId, 'refresh').then((proactive) => {
          if (!disposed && activeConversationRef.current === conversationId) {
            dispatch({ type: 'HYDRATE_PROACTIVE', payload: proactive });
          }
        }).catch((error) => console.warn('proactive bootstrap failed', error));
        dispatch({ type: 'SET_CONNECTED', payload: true });
      }
      const latestSummary = conversationsRef.current.find((item) => item.id === conversationId);
      const hasUnansweredUser = merged.length > 0 && merged[merged.length - 1]?.role === 'user';
      if ((runActive || latestSummary?.activityStatus === 'running' || hasUnansweredUser)
        && !client.hasActiveTransport()) {
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

  useEffect(() => {
    // Makers Schedule currently supports a minimum interval of one day.
    // While the product is open, this bounded browser wake-up asks the
    // Makers Agent to perform the memory-first window check every 10 minutes;
    // all state and policy decisions remain in Makers Store.
    let lastCheckedAt = Date.now();
    let refreshing = false;
    const refreshMemoryWindow = () => {
      if (refreshing || document.visibilityState !== 'visible') return;
      refreshing = true;
      lastCheckedAt = Date.now();
      void proactiveOperation(activeConversationRef.current, 'memory_refresh')
        .then((proactive) => dispatch({ type: 'HYDRATE_PROACTIVE', payload: proactive }))
        .catch((error) => console.warn('proactive memory-window refresh failed', error))
        .finally(() => { refreshing = false; });
    };
    const timer = window.setInterval(refreshMemoryWindow, 10 * 60 * 1000);
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible' && Date.now() - lastCheckedAt >= 10 * 60 * 1000) {
        refreshMemoryWindow();
      }
    };
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [dispatch]);

  return clientRef;
}
