import { useEffect, useRef } from 'react';
import { MessagePlugin } from 'tdesign-react';
import { bootstrapApp, proactiveOperation } from '../services/api';
import { withEdgeOneAuth } from '../services/auth';
import { presentableChatError } from '../services/chatError';
import { durableMessageCount, makersConversationHeaders, mergeMessages, normalizeMessages, reconcileCompletedMessage, settleStoppedMessages } from '../services/conversation';
import { splitSseFrames } from '../services/sse';
import { useAppDispatch, useAppState } from '../store/appState';
import type { ChatMessage, ClarificationPrompt, PaperInfo, ProactiveState, ScheduleItem, SearchMeta, WorkspaceAction } from '../types';
import { translate, type TranslationKey } from '../i18n';

type ClientEvent = { type: string; payload: Record<string, unknown> };

const STREAM_IDLE_TIMEOUT_MS = 20_000;
const STOP_TIMEOUT_MS = 4_000;
const MANUAL_STOP_PREFIX = 'floris:manual-stop:';

function manualStopKey(conversationId: string): string {
  return `${MANUAL_STOP_PREFIX}${conversationId}`;
}

export function readManualStopIntent(conversationId: string): boolean {
  try {
    return window.sessionStorage.getItem(manualStopKey(conversationId)) === '1';
  } catch {
    return false;
  }
}

function writeManualStopIntent(conversationId: string, stopped: boolean): void {
  try {
    if (stopped) window.sessionStorage.setItem(manualStopKey(conversationId), '1');
    else window.sessionStorage.removeItem(manualStopKey(conversationId));
  } catch {
    // In-memory state below still protects this tab when storage is disabled.
  }
}

export function terminalGenerationError(error: unknown, timedOut = false): string {
  if (timedOut) return translate('generationTimedOut');
  const value = error as { name?: unknown; message?: unknown };
  if (String(value?.name || '') === 'AbortError') {
    return translate('generationStoppedTerminal');
  }
  return String(value?.message || error || translate('generationFailedRetry'));
}

const TOOL_PROGRESS: Record<string, { active: TranslationKey; complete: TranslationKey }> = {
  rich_search: { active: 'toolRichSearchActive', complete: 'toolRichSearchComplete' },
  search_places: { active: 'toolPlacesActive', complete: 'toolPlacesComplete' },
  plan_route_between_places: { active: 'toolRouteActive', complete: 'toolRouteComplete' },
  prepare_map_recommendation: { active: 'toolMapPrepareActive', complete: 'toolMapPrepareComplete' },
  recommend_places_on_map: { active: 'toolMapRecommendActive', complete: 'toolMapRecommendComplete' },
  propose_calendar_changes: { active: 'toolCalendarActive', complete: 'toolCalendarComplete' },
  propose_meeting: { active: 'toolMeetingActive', complete: 'toolMeetingComplete' },
  propose_image: { active: 'toolImageActive', complete: 'toolImageComplete' },
  image_generation_planning: { active: 'toolImagePlanActive', complete: 'toolImagePlanComplete' },
  search_arxiv: { active: 'toolPaperActive', complete: 'toolPaperComplete' },
  collect_page_images: { active: 'toolPageImagesActive', complete: 'toolPageImagesComplete' },
  search_rich_images: { active: 'toolImageSearchActive', complete: 'toolImageSearchComplete' },
  analyze_images_parallel: { active: 'toolImageAnalyzeActive', complete: 'toolImageAnalyzeComplete' },
};

export function progressTextForTool(toolName: string, phase: 'active' | 'complete'): string {
  const key = TOOL_PROGRESS[toolName]?.[phase]
    || (phase === 'active' ? 'toolGenericActive' : 'toolGenericComplete');
  return translate(key);
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

export function actionOnlyFallback(actions: WorkspaceAction[] | undefined): string {
  const kinds = new Set((actions || []).map((action) => action.kind));
  if (kinds.has('map_recommendation')) return translate('actionMapReady');
  if (kinds.has('meeting_create')) return translate('actionMeetingReady');
  if (kinds.has('calendar_changes')) return translate('actionCalendarReady');
  if (kinds.has('image_generate')) return translate('actionImageReady');
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
  private listeners = new Set<(message: ClientEvent) => void>();
  private manualStopIntent: boolean;

  constructor(private readonly conversationId: string) {
    this.manualStopIntent = readManualStopIntent(conversationId);
  }

  private setManualStopIntent(stopped: boolean) {
    this.manualStopIntent = stopped;
    writeManualStopIntent(this.conversationId, stopped);
  }

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
    return Boolean(this.controller);
  }

  private async cancelMakerRun(): Promise<'confirmed' | 'local'> {
    const stopController = new AbortController();
    const stopTimer = window.setTimeout(() => stopController.abort(), STOP_TIMEOUT_MS);
    const requestStop = (signal?: AbortSignal) => fetch(withEdgeOneAuth('/stop'), {
      method: 'POST',
      // Makers documents that stop must not carry the target conversation
      // header, otherwise this request can replace the active run signal.
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: this.conversationId }),
      credentials: 'same-origin',
      signal,
    });
    try {
      const response = await requestStop(stopController.signal);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return 'confirmed';
    } catch {
      // Retry only the cancellation when connectivity returns. This never
      // creates a model request or resumes the failed answer.
      window.addEventListener('online', () => {
        void requestStop().catch(() => {});
      }, { once: true });
      return 'local';
    } finally {
      window.clearTimeout(stopTimer);
    }
  }

  async stop(): Promise<'confirmed' | 'local'> {
    // Record intent before aborting the transport. A stopped run is terminal;
    // only a later explicit user send may clear this marker.
    this.setManualStopIntent(true);
    this.controller?.abort();
    this.controller = null;
    // Settle the UI immediately. Makers cancellation remains the durable
    // backend operation, but it must not leave the composer locked while the
    // platform propagates the abort.
    this.emit({ type: 'stop_requested', payload: {} });
    return this.cancelMakerRun();
  }

  async send(rawMessage: unknown) {
    const message = rawMessage as { type?: string; payload?: Record<string, unknown> };
    if (message.type === 'ping') return;

    // A deliberate new message is the only action that clears a manual stop.
    // Do not call stop() here because that would persist a false user intent.
    const allowAfterStop = this.manualStopIntent;
    this.setManualStopIntent(false);
    this.controller?.abort();
    this.controller = null;
    this.controller = new AbortController();
    const signal = this.controller.signal;
    const streamId = `ai-stream-${Date.now()}`;
    let streamFinished = false;
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
        body: JSON.stringify({
          ...(message.payload || {}),
          ...(allowAfterStop ? { _allow_after_stop: true } : {}),
        }),
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
      if (!reader) throw new Error(translate('cannotReadStream'));

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
                  payload: { id: streamId, status: 'arranging', statusText: translate('arrangingReviewedImages') },
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
                  payload: { id: streamId, message: typeof event.content === 'string' ? event.content : translate('serviceError') },
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
      // Never poll the checkpoint or start another generation automatically.
      if (!protocolDone) {
        this.emit({
          type: 'error',
          payload: {
            id: streamId,
            message: translate('networkGenerationEnded'),
          },
        });
        this.setManualStopIntent(true);
        void this.cancelMakerRun();
      }
      finish();
    } catch (error) {
      const explicitlyStopped = this.manualStopIntent && (error as Error).name === 'AbortError';
      if (!explicitlyStopped) {
        this.emit({
          type: 'error',
          payload: { id: streamId, message: terminalGenerationError(error, watchdogTriggered) },
        });
        this.setManualStopIntent(true);
        void this.cancelMakerRun();
      }
      finish();
    } finally {
      if (idleWatchdog) window.clearTimeout(idleWatchdog);
      if (this.controller?.signal === signal) this.controller = null;
    }
  }

  close() {
    // Unmount/refresh only detaches this page. Explicit user cancellation is
    // handled by stop(); never turn a browser refresh into a server-side stop.
    this.controller?.abort();
    this.controller = null;
  }
}

const MESSAGE_CACHE_PREFIX = 'yuanbao.messages.';

function readMessageCache(conversationId: string): ChatMessage[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(`${MESSAGE_CACHE_PREFIX}${conversationId}`) || '[]') as ChatMessage[];
    return Array.isArray(parsed)
      ? parsed.filter((item) => !item.failed && (item.role === 'user' || item.content.trim() || Boolean(item.clarification))).map((item) => ({ ...item, streaming: false }))
      : [];
  } catch { return []; }
}

function writeMessageCache(conversationId: string, messages: ChatMessage[]) {
  const durable = messages.filter((item) => !item.failed && (item.role === 'user' || item.content.trim() || Boolean(item.clarification)));
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
  const pageOpenProactiveRefreshStartedRef = useRef(false);
  activeConversationRef.current = conversationId;
  conversationsRef.current = conversations;

  const setConversationActivity = (id: string, activityStatus: 'idle' | 'running' | 'failed') => {
    const now = Date.now();
    const previous = conversationsRef.current.find((item) => item.id === id);
    const messageCount = durableMessageCount(cached(id));
    const next = {
      id,
      title: previous?.title || translate('newConversation'),
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
            skill: { intent: 'chat', mode: 'immediate', content: '', icon: '✨', action_label: '', params: {}, data: { status: 'thinking', statusText: translate('understandingRequest') } },
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
        case 'search_status': {
          const current = streams.get(streamId); if (!current) break;
          const intent = event.payload.intent === 'image' || current.skill?.intent === 'image' ? 'image' : 'search';
          const skill = { intent, mode: 'immediate', content: '', icon: intent === 'image' ? '🎨' : '🔍', action_label: '', params: {}, data: { status: String(event.payload.status || 'searching'), statusText: String(event.payload.statusText || translate('processingInformation')) } } as ChatMessage['skill'];
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
                data: { ...current.skill.data, status: 'error', statusText: translate('processingFailedStatus') },
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
      const liveTransport = client.hasActiveTransport();
      const merged = mergeMessages(data.messages, cached(conversationId), {
        preserveStreaming: runActive && liveTransport,
      });
      const hasFinalAnswer = merged[merged.length - 1]?.role === 'ai'
        && Boolean(merged[merged.length - 1]?.content.trim());
      const hasUnansweredUser = merged[merged.length - 1]?.role === 'user';
      let visibleMessages = liveTransport ? merged : settleStoppedMessages(merged);
      if (!liveTransport && (runActive || hasUnansweredUser)) {
        // A reload or lost browser connection must never silently resume an
        // earlier model run. Stop the orphaned Maker run and render one
        // explicit failure row; only the user's Retry button can send again.
        if (runActive) void client.stop();
        if (!hasFinalAnswer) {
          visibleMessages = [
            ...visibleMessages,
            {
              id: `ai-interrupted-${data.run?.run_id || Date.now()}`,
              role: 'ai',
              content: translate('previousGenerationStopped'),
              ts: Date.now(),
              streaming: false,
              failed: true,
              skill: {
                intent: 'chat',
                mode: 'immediate',
                content: '',
                icon: '✨',
                action_label: '',
                params: {},
                data: { status: 'error', statusText: translate('generationStoppedStatus') },
              },
            },
          ];
        }
      }
      publish(conversationId, visibleMessages);
      const summary = conversationsRef.current.find((item) => item.id === conversationId);
      if (summary && summary.messageCount !== visibleMessages.length) {
        const reconciled = {
          ...summary,
          messageCount: visibleMessages.length,
          activityStatus: !liveTransport && (runActive || hasUnansweredUser) ? 'failed' as const : summary.activityStatus,
        };
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
        const proactiveOperationName = pageOpenProactiveRefreshStartedRef.current ? 'get' : 'page_open';
        pageOpenProactiveRefreshStartedRef.current = true;
        void proactiveOperation(conversationId, proactiveOperationName).then((proactive) => {
          if (!disposed && activeConversationRef.current === conversationId) {
            dispatch({ type: 'HYDRATE_PROACTIVE', payload: proactive });
          }
        }).catch((error) => console.warn('proactive bootstrap failed', error));
        dispatch({ type: 'SET_CONNECTED', payload: true });
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
