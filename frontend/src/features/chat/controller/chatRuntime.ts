import { useEffect, useRef } from 'react';
import { MessagePlugin } from 'tdesign-react';
import { bootstrapApp } from '../model/client';
import { proactiveOperation } from '../../settings/model/client';
import { presentableChatError } from '../../../services/chatError';
import { durableMessageCount, hasDurableAssistantPayload, isDurableChatMessage, mergeMessages, normalizeMessages, reconcileCompletedMessage, settleStoppedMessages } from '../../../services/conversation';
import { useAppDispatch, useAppState } from '../../../store/appState';
import type { ChatMessage, ClarificationPrompt, PaperInfo, ProactiveState, ScheduleItem, SearchMeta, StructuredProgressStep, WorkspaceAction } from '../model';
import { translate } from '../../../i18n';
import {
  initialPlanningProgress,
  mergeProgressStep,
} from '../../search/model/progressModel';
import { mergeSearchMeta, resolveSearchStartAt } from '../../search/model/searchRuntime';
import { SSEChatClient } from './chatTransport';
import {
  actionOnlyFallback,
  restoredConversationWasInterrupted,
  shouldPersistRenderedMessages,
} from './chatRuntimeModel';

export {
  CHAT_INITIAL_RESPONSE_TIMEOUT_MS,
  canStartChatTransport,
  locationRetryMessage,
  progressTextForTool,
  readManualStopIntent,
  terminalGenerationError,
} from './chatTransport';
export {
  actionOnlyFallback,
  isConversationGenerationActive,
  restoredConversationWasInterrupted,
  shouldPersistRenderedMessages,
} from './chatRuntimeModel';
export { mergeSearchMeta, resolveSearchStartAt } from '../../search/model/searchRuntime';

const MESSAGE_CACHE_PREFIX = 'yuanbao.messages.';

function readMessageCache(conversationId: string): ChatMessage[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(`${MESSAGE_CACHE_PREFIX}${conversationId}`) || '[]') as ChatMessage[];
    return Array.isArray(parsed)
      ? parsed.filter(isDurableChatMessage).map((item) => ({ ...item, streaming: false }))
      : [];
  } catch { return []; }
}

function writeMessageCache(conversationId: string, messages: ChatMessage[]) {
  const durable = messages.filter(isDurableChatMessage);
  try { localStorage.setItem(`${MESSAGE_CACHE_PREFIX}${conversationId}`, JSON.stringify(durable.slice(-60))); }
  catch { /* Remote checkpoints remain the durable fallback. */ }
}

export function useChatRuntime() {
  const { conversationId, messages, conversations } = useAppState();
  const dispatch = useAppDispatch();
  const clientRef = useRef<SSEChatClient | null>(null);
  const clientsRef = useRef(new Map<string, { client: SSEChatClient; off: () => void }>());
  const cacheRef = useRef(new Map<string, ChatMessage[]>());
  const streamsRef = useRef(new Map<string, Map<string, ChatMessage>>());
  // Search timing belongs to one live turn, not to whichever progress event
  // happened to render last. Keep the bounds outside the message merge path
  // so bootstrap/reconciliation cannot reset the visible stopwatch.
  const searchStartedAtRef = useRef(new Map<string, number>());
  const searchCompletedAtRef = useRef(new Map<string, number>());
  const pendingTurnStartedAtRef = useRef(new Map<string, number>());
  const activeConversationRef = useRef(conversationId);
  const renderedMessagesOwnerRef = useRef(conversationId);
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

  const rememberSearchStart = (streamId: string, current: ChatMessage, shouldStart: boolean) => {
    const known = resolveSearchStartAt(
      current.searchStartedAt,
      searchStartedAtRef.current.get(streamId),
      shouldStart,
      Number(current.turnStartedAt || Date.now()),
    );
    if (known) {
      searchStartedAtRef.current.set(streamId, known);
      return known;
    }
    return undefined;
  };

  const rememberedSearchCompletion = (streamId: string, current: ChatMessage) => (
    searchCompletedAtRef.current.get(streamId) || Number(current.searchCompletedAt || 0) || undefined
  );

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
          pendingTurnStartedAtRef.current.set(
            id,
            Number(message.ts || Date.now()),
          );
          const current = cached(id);
          publish(id, current.some((item) => item.id === message.id) ? current : [...current, message]);
          break;
        }
        case 'clarification_submitted': {
          const messageId = String(event.payload.message_id || '');
          if (!messageId) break;
          publish(id, cached(id).map((item) => (
            item.id === messageId ? { ...item, clarificationAnswered: true } : item
          )));
          break;
        }
        case 'stream_start': {
          const turnStartedAt = pendingTurnStartedAtRef.current.get(id)
            || Date.now();
          pendingTurnStartedAtRef.current.delete(id);
          const streamMessage: ChatMessage = {
            id: streamId || `ai-stream-${Date.now()}`, role: 'ai', content: '', ts: Date.now(), streaming: true,
            turnStartedAt,
            skill: { intent: 'chat', mode: 'immediate', content: '', icon: '✨', action_label: '', params: {}, data: { status: 'thinking', statusText: translate('understandingRequest') } },
            progress: [initialPlanningProgress()],
          };
          searchStartedAtRef.current.delete(streamMessage.id);
          searchCompletedAtRef.current.delete(streamMessage.id);
          streams.set(streamMessage.id, streamMessage);
          const current = cached(id).filter((item) => item.id !== streamMessage.id && !item.failed);
          publish(id, [...current, streamMessage]);
          setConversationActivity(id, 'running');
          break;
        }
        case 'stream_delta': {
          const current = streams.get(streamId); const delta = String(event.payload.delta || '');
          if (current && delta) {
            const searchStartedAt = rememberSearchStart(streamId, current, false);
            const searchCompletedAt = rememberedSearchCompletion(streamId, current);
            const next = {
              ...current,
              content: current.content + delta,
              ...(searchStartedAt ? { searchStartedAt } : {}),
              ...(searchCompletedAt ? { searchCompletedAt } : {}),
            };
            streams.set(streamId, next);
            patch(id, streamId, {
              ...(searchStartedAt ? { searchStartedAt } : {}),
              ...(searchCompletedAt ? { searchCompletedAt } : {}),
            }, delta);
          }
          break;
        }
        case 'stream_reset': {
          const current = streams.get(streamId);
          if (current) {
            const searchStartedAt = rememberSearchStart(streamId, current, false);
            const searchCompletedAt = rememberedSearchCompletion(streamId, current);
            const next = {
              ...current,
              content: '',
              ...(searchStartedAt ? { searchStartedAt } : {}),
              ...(searchCompletedAt ? { searchCompletedAt } : {}),
            };
            streams.set(streamId, next);
            patch(id, streamId, {
              content: '',
              ...(searchStartedAt ? { searchStartedAt } : {}),
              ...(searchCompletedAt ? { searchCompletedAt } : {}),
            });
          }
          break;
        }
        case 'stream_end': {
          const current = streams.get(streamId);
          if (current) {
            streams.delete(streamId);
            if (current.failed) {
              searchStartedAtRef.current.delete(streamId);
              searchCompletedAtRef.current.delete(streamId);
              break;
            }
            if (!isDurableChatMessage(current)) {
              publish(id, cached(id).filter((item) => item.id !== streamId));
              searchStartedAtRef.current.delete(streamId);
              searchCompletedAtRef.current.delete(streamId);
              setConversationActivity(id, 'idle');
              break;
            }
            const searchStartedAt = rememberSearchStart(streamId, current, false);
            const searchCompletedAt = rememberedSearchCompletion(streamId, current)
              || (searchStartedAt ? Date.now() : undefined);
            const complete = {
              ...current,
              content: current.content.trim() ? current.content : actionOnlyFallback(current.workspaceActions),
              streaming: false,
              ...(searchStartedAt ? { searchStartedAt } : {}),
              ...(searchCompletedAt ? { searchCompletedAt } : {}),
            };
            publish(id, reconcileCompletedMessage(cached(id), complete));
            searchStartedAtRef.current.delete(streamId);
            searchCompletedAtRef.current.delete(streamId);
            setConversationActivity(id, 'idle');
          }
          break;
        }
        case 'answer_complete': {
          const current = streams.get(streamId);
          if (current) {
            const searchStartedAt = rememberSearchStart(streamId, current, false);
            const searchCompletedAt = searchStartedAt
              ? rememberedSearchCompletion(streamId, current) || Date.now()
              : undefined;
            if (searchCompletedAt) searchCompletedAtRef.current.set(streamId, searchCompletedAt);
            const next = {
              ...current,
              streaming: false,
              ...(searchStartedAt ? { searchStartedAt } : {}),
              ...(searchCompletedAt ? { searchCompletedAt } : {}),
            };
            streams.set(streamId, next);
            patch(id, streamId, {
              streaming: false,
              ...(searchStartedAt ? { searchStartedAt } : {}),
              ...(searchCompletedAt ? { searchCompletedAt } : {}),
            });
          }
          break;
        }
        case 'experience_hint': {
          const current = streams.get(streamId);
          const items = Array.isArray(event.payload.items)
            ? event.payload.items as ChatMessage['experienceHints']
            : [];
          if (current && items?.length) {
            const next = { ...current, experienceHints: items };
            streams.set(streamId, next);
            patch(id, streamId, { experienceHints: items });
          }
          break;
        }
        case 'stop_requested': {
          streams.clear();
          searchStartedAtRef.current.clear();
          searchCompletedAtRef.current.clear();
          pendingTurnStartedAtRef.current.delete(id);
          publish(id, settleStoppedMessages(cached(id)));
          setConversationActivity(id, 'idle');
          break;
        }
        case 'search_status': {
          const current = streams.get(streamId); if (!current) break;
          const toolName = String(event.payload.toolName || '');
          const isImage = event.payload.intent === 'image' || current.skill?.intent === 'image';
          const isSearch = toolName === 'rich_search' || current.skill?.intent === 'search';
          const intent = isImage ? 'image' : isSearch ? 'search' : 'chat';
          const skill = { intent, mode: 'immediate', content: '', icon: intent === 'image' ? '🎨' : '🔍', action_label: '', params: {}, data: { status: String(event.payload.status || 'searching'), statusText: String(event.payload.statusText || translate('processingInformation')) } } as ChatMessage['skill'];
          const searchStartedAt = rememberSearchStart(streamId, current, !isImage && isSearch);
          const searchCompletedAt = rememberedSearchCompletion(streamId, current);
          const next = {
            ...current,
            skill,
            ...(searchStartedAt ? { searchStartedAt } : {}),
            ...(searchCompletedAt ? { searchCompletedAt } : {}),
          };
          streams.set(streamId, next);
          patch(id, streamId, {
            skill,
            ...(searchStartedAt ? { searchStartedAt } : {}),
            ...(searchCompletedAt ? { searchCompletedAt } : {}),
          });
          break;
        }
        case 'progress_event': {
          const current = streams.get(streamId);
          const step = event.payload.step as StructuredProgressStep | undefined;
          if (!current || !step) break;
          const progress = mergeProgressStep(current.progress, step);
          const searchActivity = step.activity === 'web_search'
            || step.activity === 'paper_search'
            || step.activity === 'place_search';
          const searchStartedAt = rememberSearchStart(streamId, current, searchActivity);
          const searchCompletedAt = rememberedSearchCompletion(streamId, current);
          const next = {
            ...current,
            progress,
            ...(searchStartedAt ? { searchStartedAt } : {}),
            ...(searchCompletedAt ? { searchCompletedAt } : {}),
          };
          streams.set(streamId, next);
          patch(id, streamId, {
            progress,
            ...(searchStartedAt ? { searchStartedAt } : {}),
            ...(searchCompletedAt ? { searchCompletedAt } : {}),
          });
          break;
        }
        case 'search_results': {
          const current = streams.get(streamId); const incoming = event.payload as unknown as Partial<SearchMeta>;
          if (current && Array.isArray(incoming.results)) {
            const searchResults = mergeSearchMeta(current.searchResults, incoming);
            const searchStartedAt = rememberSearchStart(streamId, current, true);
            const searchCompletedAt = rememberedSearchCompletion(streamId, current);
            streams.set(streamId, {
              ...current,
              searchResults,
              ...(searchStartedAt ? { searchStartedAt } : {}),
              ...(searchCompletedAt ? { searchCompletedAt } : {}),
            });
            patch(id, streamId, {
              searchResults,
              ...(searchStartedAt ? { searchStartedAt } : {}),
              ...(searchCompletedAt ? { searchCompletedAt } : {}),
            });
          }
          break;
        }
        case 'search_media': {
          // Media review is intentionally progressive and can finish just
          // after the text stream closes. Hydrate the completed durable row
          // as well as a live stream so reviewed images are never dropped at
          // that boundary.
          const live = streams.get(streamId);
          const current = live || cached(id).find((item) => item.id === streamId);
          if (!current) break;
          const searchResults = mergeSearchMeta(current.searchResults, {
            query: String(event.payload.query || ''),
            media: Array.isArray(event.payload.media) ? event.payload.media : [],
            images: Array.isArray(event.payload.images) ? event.payload.images : [],
            media_pending: false,
            vision_diagnostics: event.payload.vision_diagnostics as Record<string, number> | undefined,
            timings_ms: event.payload.timings_ms as Record<string, number> | undefined,
          } as Partial<SearchMeta>);
          const searchStartedAt = rememberSearchStart(streamId, current, true);
          const searchCompletedAt = rememberedSearchCompletion(streamId, current);
          const next = {
            ...current,
            searchResults,
            ...(searchStartedAt ? { searchStartedAt } : {}),
            ...(searchCompletedAt ? { searchCompletedAt } : {}),
          };
          if (live) streams.set(streamId, next);
          publish(id, cached(id).map((item) => item.id === streamId ? next : item));
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
            const searchStartedAt = rememberSearchStart(streamId, current, false);
            const searchCompletedAt = searchStartedAt
              ? rememberedSearchCompletion(streamId, current) || Date.now()
              : undefined;
            if (searchCompletedAt) searchCompletedAtRef.current.set(streamId, searchCompletedAt);
            const next = {
              ...current,
              content: message,
              streaming: false,
              failed: true,
              ...(searchStartedAt ? { searchStartedAt } : {}),
              ...(searchCompletedAt ? { searchCompletedAt } : {}),
              skill: current.skill ? {
                ...current.skill,
                data: { ...current.skill.data, status: 'error', statusText: translate('processingFailedStatus') },
              } : current.skill,
            };
            streams.set(streamId, next);
            patch(id, streamId, {
              content: message,
              streaming: false,
              failed: true,
              skill: next.skill,
              ...(searchStartedAt ? { searchStartedAt } : {}),
              ...(searchCompletedAt ? { searchCompletedAt } : {}),
            });
          }
          setConversationActivity(id, 'failed');
          if (activeConversationRef.current === id) MessagePlugin.error(translate('answerGenerationFailedToast'));
          break;
        }
      }
    });
    clientsRef.current.set(id, { client, off });
    return client;
  };

  useEffect(() => {
    const renderedOwner = renderedMessagesOwnerRef.current;
    renderedMessagesOwnerRef.current = conversationId;
    if (!shouldPersistRenderedMessages(renderedOwner, conversationId)) return;
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
      const hasUnansweredUser = merged[merged.length - 1]?.role === 'user';
      const interrupted = restoredConversationWasInterrupted(
        merged,
        runActive,
        liveTransport,
      );
      let visibleMessages = liveTransport ? merged : settleStoppedMessages(merged);
      if (!liveTransport && (runActive || hasUnansweredUser)) {
        // A reload or lost browser connection must never silently resume an
        // earlier model run. Stop the orphaned Maker run and render one
        // explicit failure row; only the user's Retry button can send again.
        if (runActive) void client.stop();
        if (interrupted) {
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
      const restoredActivityStatus = interrupted
        ? 'failed' as const
        : hasDurableAssistantPayload(visibleMessages[visibleMessages.length - 1])
          ? 'idle' as const
          : summary?.activityStatus;
      if (
        summary
        && (
          summary.messageCount !== visibleMessages.length
          || summary.activityStatus !== restoredActivityStatus
        )
      ) {
        const reconciled = {
          ...summary,
          messageCount: visibleMessages.length,
          activityStatus: restoredActivityStatus,
        };
        conversationsRef.current = conversationsRef.current.map((item) => (
          item.id === conversationId ? reconciled : item
        ));
        dispatch({ type: 'UPSERT_CONVERSATION', payload: reconciled });
      }
      if (activeConversationRef.current === conversationId) {
        dispatch({
          type: 'HYDRATE_WORKSPACE',
          payload: {
            schedules: data.schedules,
            mapPlaces: data.map_places,
            mapTitle: data.map_title,
            mapRouteMode: data.map_route_mode || undefined,
            mapRouteStrategy: data.map_route_strategy || undefined,
            mapRoute: data.map_route,
            mapShowRoute: data.map_show_route,
          },
        });
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
    window.addEventListener('yuanbao:proactive-refresh', refreshProactive);
    return () => {
      window.removeEventListener('yuanbao:workspace-changed', refreshWorkspace);
      window.removeEventListener('yuanbao:proactive-refresh', refreshProactive);
    };
  }, [dispatch]);

  useEffect(() => {
    // Makers Schedule currently supports a minimum interval of one day.
    // While the product is open, this bounded browser wake-up asks the
    // Makers Agent to perform the memory-first window check every 5 minutes;
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
    const timer = window.setInterval(refreshMemoryWindow, 5 * 60 * 1000);
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible' && Date.now() - lastCheckedAt >= 5 * 60 * 1000) {
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
