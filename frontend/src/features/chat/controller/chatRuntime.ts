import { useEffect, useRef } from 'react';
import { MessagePlugin } from 'tdesign-react';
import { bootstrapApp } from '../model/client';
import { proactiveOperation } from '../../settings/model/client';
import { presentableChatError } from '../../../services/chatError';
import { discardTurnAnswer, durableMessageCount, isDurableChatMessage, mergeMessages, normalizeMessages, reconcileCompletedMessage, settleStoppedMessages } from '../../../services/conversation';
import { useAppDispatch, useAppState } from '../../../store/appState';
import type { BootstrapData, ChatMessage, ChatQueueItem, ClarificationPrompt, PaperInfo, ProactiveState, RunPresentationSnapshot, ScheduleItem, SearchMeta, StructuredProgressStep, WorkspaceAction } from '../model';
import { translate } from '../../../i18n';
import {
  initialPlanningProgress,
  mergeProgressStep,
  normalizeProgressEvent,
} from '../../search/model/progressModel';
import { mergeSearchMeta, resolveSearchStartAt, restoredPresentationTiming } from '../../search/model/searchRuntime';
import { SSEChatClient } from './chatTransport';
import { readManualStopClientMessageId, readManualStopIntent } from './turnControl';
import {
  actionOnlyFallback,
  messagesForDurableCache,
  shouldPersistRenderedMessages,
} from './chatRuntimeModel';

export {
  CHAT_INITIAL_RESPONSE_TIMEOUT_MS,
  canStartChatTransport,
  locationRetryMessage,
  progressTextForTool,
  terminalGenerationError,
} from './chatTransport';
export { readManualStopClientMessageId, readManualStopIntent } from './turnControl';
export {
  actionOnlyFallback,
  isConversationGenerationActive,
  messagesForDurableCache,
  shouldPersistRenderedMessages,
} from './chatRuntimeModel';
export { restoredConversationWasInterrupted } from './chatRuntimeModel';
export { mergeSearchMeta, resolveSearchStartAt } from '../../search/model/searchRuntime';

const MESSAGE_CACHE_PREFIX = 'yuanbao.messages.';
const LIVE_MESSAGE_CACHE_PREFIX = 'yuanbao.live-messages.';
const LIVE_MESSAGE_CACHE_TTL_MS = 45 * 60 * 1000;
const liveCacheWrittenAt = new Map<string, number>();

function readMessageCache(conversationId: string): ChatMessage[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(`${MESSAGE_CACHE_PREFIX}${conversationId}`) || '[]') as ChatMessage[];
    const durable = Array.isArray(parsed)
      ? parsed.filter(isDurableChatMessage).map((item) => ({ ...item, streaming: false }))
      : [];
    if (readManualStopIntent(conversationId)) return durable;
    const live = JSON.parse(
      localStorage.getItem(`${LIVE_MESSAGE_CACHE_PREFIX}${conversationId}`) || 'null',
    ) as { updatedAt?: number; messages?: ChatMessage[] } | null;
    if (
      live
      && Date.now() - Number(live.updatedAt || 0) <= LIVE_MESSAGE_CACHE_TTL_MS
      && Array.isArray(live.messages)
      && live.messages.some((item) => item.role === 'ai' && item.streaming)
    ) return normalizeMessages(live.messages.filter((item) => !item.failed && !item.queued));
    return durable;
  } catch { return []; }
}

function writeMessageCache(conversationId: string, messages: ChatMessage[]) {
  // Live assistant deltas are a presentation buffer.  Persist only after the
  // server emits the terminal completion boundary, otherwise a conversation
  // switch can resurrect text that the user deliberately stopped.
  const durable = messagesForDurableCache(messages);
  try {
    const durableKey = `${MESSAGE_CACHE_PREFIX}${conversationId}`;
    const serialized = JSON.stringify(durable.slice(-60));
    if (localStorage.getItem(durableKey) !== serialized) {
      localStorage.setItem(durableKey, serialized);
    }
    const liveKey = `${LIVE_MESSAGE_CACHE_PREFIX}${conversationId}`;
    if (messages.some((item) => item.role === 'ai' && item.streaming)) {
      const now = Date.now();
      if (now - Number(liveCacheWrittenAt.get(conversationId) || 0) >= 140) {
        localStorage.setItem(liveKey, JSON.stringify({
          updatedAt: now,
          messages: messages.filter((item) => !item.failed && !item.queued).slice(-60),
        }));
        liveCacheWrittenAt.set(conversationId, now);
      }
    } else {
      localStorage.removeItem(liveKey);
      liveCacheWrittenAt.delete(conversationId);
    }
  }
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
          publish(id, current.some((item) => item.id === message.id)
            ? current.map((item) => item.id === message.id ? { ...item, ...message } : item)
            : [...current, message]);
          if (activeConversationRef.current === id) {
            window.dispatchEvent(new CustomEvent('floris:question-sent', {
              detail: { conversationId: id, messageId: message.id },
            }));
          }
          const previous = conversationsRef.current.find((item) => item.id === id);
          const title = message.content.trim();
          const summary = {
            id,
            title: previous?.pending
              ? title.slice(0, 64)
              : (previous?.title || title.slice(0, 64)),
            createdAt: previous?.createdAt || Date.now(),
            updatedAt: Date.now(),
            messageCount: Math.max(1, Number(previous?.messageCount || 0) + 1),
            pending: false,
            activityStatus: 'running' as const,
          };
          conversationsRef.current = [summary, ...conversationsRef.current.filter((item) => item.id !== id)];
          dispatch({ type: 'UPSERT_CONVERSATION', payload: summary });
          break;
        }
        case 'queue_changed': {
          if (activeConversationRef.current === id) {
            dispatch({
              type: 'SET_TURN_QUEUE',
              payload: Array.isArray(event.payload.items)
                ? event.payload.items as ChatQueueItem[]
                : [],
            });
          }
          break;
        }
        case 'turn_started': {
          const clientMessageId = String(event.payload.client_message_id || '');
          if (clientMessageId) {
            publish(id, cached(id).map((item) => (
              item.id === clientMessageId ? { ...item, queued: false } : item
            )));
          }
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
          const ownerClientMessageId = String(event.payload.client_message_id || '');
          const turnStartedAt = pendingTurnStartedAtRef.current.get(id)
            || Date.now();
          pendingTurnStartedAtRef.current.delete(id);
          const streamMessage: ChatMessage = {
            id: streamId || `ai-stream-${Date.now()}`, role: 'ai', content: '', ts: Date.now(), streaming: true,
            turnStartedAt,
            client_message_id: ownerClientMessageId || undefined,
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
          const stoppedClientMessageId = String(event.payload.client_message_id || '');
          if (streamId) streams.delete(streamId);
          else streams.clear();
          if (streamId) {
            searchStartedAtRef.current.delete(streamId);
            searchCompletedAtRef.current.delete(streamId);
          }
          pendingTurnStartedAtRef.current.delete(id);
          publish(id, discardTurnAnswer(cached(id), stoppedClientMessageId, streamId));
          setConversationActivity(id, 'idle');
          break;
        }
        case 'transport_recovering': {
          const current = streams.get(streamId);
          if (!current) break;
          const skill = {
            ...(current.skill || { intent: 'chat', mode: 'immediate', content: '', icon: '', action_label: '', params: {}, data: {} }),
            data: {
              ...(current.skill?.data || {}),
              status: 'recovering',
              statusText: translate('recoveringGeneration'),
            },
          } as ChatMessage['skill'];
          streams.set(streamId, { ...current, skill });
          patch(id, streamId, { skill });
          break;
        }
        case 'stream_snapshot': {
          const current = streams.get(streamId);
          const snapshot = event.payload.snapshot as RunPresentationSnapshot | undefined;
          if (!current || !snapshot) break;
          let searchResults = current.searchResults;
          if (snapshot.search_results) {
            searchResults = mergeSearchMeta(searchResults, snapshot.search_results);
          }
          if (snapshot.search_media) {
            searchResults = mergeSearchMeta(searchResults, {
              ...snapshot.search_media,
              media_pending: false,
            });
          }
          const progress = Array.isArray(snapshot.progress) && snapshot.progress.length
            ? snapshot.progress as unknown as StructuredProgressStep[]
            : current.progress;
          const timing = restoredPresentationTiming(snapshot, current, progress || [], current.ts);
          if (timing.searchStartedAt) searchStartedAtRef.current.set(streamId, timing.searchStartedAt);
          if (timing.searchCompletedAt) searchCompletedAtRef.current.set(streamId, timing.searchCompletedAt);
          const skill = timing.searchSelected ? {
            ...(current.skill || { mode: 'immediate', content: '', action_label: '', params: {}, data: {} }),
            intent: 'search',
            icon: '🔍',
            data: {
              ...(current.skill?.data || {}),
              status: 'searching',
              statusText: translate('processingInformation'),
            },
          } as ChatMessage['skill'] : current.skill;
          const next: ChatMessage = {
            ...current,
            content: String(snapshot.content ?? current.content),
            streaming: true,
            progress,
            turnStartedAt: timing.turnStartedAt,
            ...(skill ? { skill } : {}),
            ...(searchResults ? { searchResults } : {}),
            ...(snapshot.workspace_actions?.length
              ? { workspaceActions: snapshot.workspace_actions }
              : {}),
            ...(snapshot.clarification ? { clarification: snapshot.clarification } : {}),
            ...(snapshot.papers?.papers?.length ? { papers: snapshot.papers.papers } : {}),
            ...(snapshot.follow_ups?.length ? { followUps: snapshot.follow_ups } : {}),
            ...(snapshot.experience_hints?.length
              ? { experienceHints: snapshot.experience_hints }
              : {}),
            ...(timing.searchStartedAt ? { searchStartedAt: timing.searchStartedAt } : {}),
            ...(timing.searchCompletedAt ? { searchCompletedAt: timing.searchCompletedAt } : {}),
          };
          streams.set(streamId, next);
          publish(id, cached(id).map((item) => item.id === streamId ? next : item));
          break;
        }
        case 'recovery_snapshot': {
          const data = event.payload.data as BootstrapData | undefined;
          if (!data) break;
          streams.delete(streamId);
          searchStartedAtRef.current.delete(streamId);
          searchCompletedAtRef.current.delete(streamId);
          const withoutPlaceholder = cached(id).filter((item) => item.id !== streamId);
          publish(id, mergeMessages(data.messages || [], withoutPlaceholder));
          setConversationActivity(id, 'idle');
          if (activeConversationRef.current === id) {
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
          }
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
    dispatch({ type: 'SET_TURN_QUEUE', payload: client.queuedTurns() });
    dispatch({ type: 'HYDRATE_MESSAGES', payload: local });
    void bootstrapApp(conversationId).then((data) => {
      if (disposed) return;
      const runActive = data.run?.status === 'running' || data.run?.status === 'cancel_requested';
      const liveTransport = client.hasActiveTransport();
      const merged = mergeMessages(data.messages, cached(conversationId), {
        preserveStreaming: runActive,
      });
      const stoppedBeforeReload = readManualStopIntent(conversationId);
      const safelyMerged = stoppedBeforeReload
        ? discardTurnAnswer(
            merged,
            readManualStopClientMessageId(conversationId)
              || String(data.run?.client_message_id || ''),
          )
        : merged;
      let visibleMessages = liveTransport ? safelyMerged : settleStoppedMessages(safelyMerged);
      let restoredStreamId = '';
      if (!liveTransport && runActive) {
        const presentation = data.presentation;
        const restoredProgress = (presentation?.progress || [])
          .map((step) => normalizeProgressEvent(step))
          .filter((step): step is StructuredProgressStep => Boolean(step));
        const restoredTiming = presentation
          ? restoredPresentationTiming(presentation, {}, restoredProgress)
          : null;
        const activeClientMessageId = String(data.run?.client_message_id || '');
        const boundary = visibleMessages.length;
        let activeAiIndex = visibleMessages.findIndex((item) => (
          item.role === 'ai'
          && activeClientMessageId
          && item.client_message_id === activeClientMessageId
        ));
        if (activeAiIndex < 0) {
          for (let index = boundary - 1; index >= 0; index -= 1) {
            if (visibleMessages[index].role === 'user') break;
            if (visibleMessages[index].role === 'ai') {
              activeAiIndex = index;
              break;
            }
          }
        }
        if (activeAiIndex >= 0) {
          restoredStreamId = visibleMessages[activeAiIndex].id;
          visibleMessages = visibleMessages.map((item, index) => (
            index === activeAiIndex ? { ...item, streaming: true } : item
          ));
        } else {
          restoredStreamId = `ai-recover-${data.run?.run_id || Date.now()}`;
          const placeholder: ChatMessage = {
            id: restoredStreamId,
            role: 'ai',
            content: '',
            ts: Date.now(),
            streaming: true,
            ...(restoredTiming ? { turnStartedAt: restoredTiming.turnStartedAt } : {}),
            ...(restoredTiming?.searchStartedAt ? { searchStartedAt: restoredTiming.searchStartedAt } : {}),
            ...(restoredTiming?.searchCompletedAt ? { searchCompletedAt: restoredTiming.searchCompletedAt } : {}),
            client_message_id: activeClientMessageId || undefined,
            skill: {
              intent: restoredTiming?.searchSelected ? 'search' : 'chat',
              mode: 'immediate',
              content: '',
              icon: restoredTiming?.searchSelected ? '🔍' : '',
              action_label: '',
              params: {},
              data: { status: 'recovering', statusText: translate('recoveringGeneration') },
            },
            progress: restoredProgress.length ? restoredProgress : [initialPlanningProgress()],
          };
          visibleMessages = [
            ...visibleMessages.slice(0, boundary),
            placeholder,
            ...visibleMessages.slice(boundary),
          ];
        }
        if (restoredStreamId && presentation) {
          visibleMessages = visibleMessages.map((item) => {
            if (item.id !== restoredStreamId) return item;
            let searchResults = item.searchResults;
            if (presentation.search_results) {
              searchResults = mergeSearchMeta(searchResults, presentation.search_results);
            }
            if (presentation.search_media) {
              searchResults = mergeSearchMeta(searchResults, {
                ...presentation.search_media,
                media_pending: false,
              });
            }
            const progress = restoredProgress;
            const timing = restoredPresentationTiming(presentation, item, progress, item.ts);
            const skill = timing.searchSelected ? {
              ...(item.skill || { mode: 'immediate', content: '', action_label: '', params: {}, data: {} }),
              intent: 'search',
              icon: '🔍',
              data: {
                ...(item.skill?.data || {}),
                status: 'recovering',
                statusText: translate('recoveringGeneration'),
              },
            } as ChatMessage['skill'] : item.skill;
            return {
              ...item,
              content: String(presentation.content ?? item.content),
              streaming: true,
              turnStartedAt: timing.turnStartedAt,
              ...(skill ? { skill } : {}),
              ...(progress.length ? { progress } : {}),
              ...(timing.searchStartedAt ? { searchStartedAt: timing.searchStartedAt } : {}),
              ...(timing.searchCompletedAt ? { searchCompletedAt: timing.searchCompletedAt } : {}),
              ...(searchResults ? { searchResults } : {}),
              ...(presentation.workspace_actions?.length
                ? { workspaceActions: presentation.workspace_actions }
                : {}),
              ...(presentation.clarification
                ? { clarification: presentation.clarification }
                : {}),
              ...(presentation.papers?.papers?.length
                ? { papers: presentation.papers.papers }
                : {}),
              ...(presentation.follow_ups?.length
                ? { followUps: presentation.follow_ups }
                : {}),
              ...(presentation.experience_hints?.length
                ? { experienceHints: presentation.experience_hints }
                : {}),
            };
          });
        }
        const restoredStream = visibleMessages.find((item) => item.id === restoredStreamId);
        if (restoredStreamId && restoredStream) {
          if (restoredStream.searchStartedAt) searchStartedAtRef.current.set(restoredStreamId, restoredStream.searchStartedAt);
          if (restoredStream.searchCompletedAt) searchCompletedAtRef.current.set(restoredStreamId, restoredStream.searchCompletedAt);
          streamsRef.current.get(conversationId)?.set(restoredStreamId, restoredStream);
        }
      } else if (data.run?.status === 'cancelled') {
        visibleMessages = discardTurnAnswer(
          visibleMessages,
          String(data.run.client_message_id || ''),
        );
      }
      publish(conversationId, visibleMessages);
      const summary = conversationsRef.current.find((item) => item.id === conversationId);
      const restoredActivityStatus = runActive
        ? 'running' as const
        : data.run?.status === 'failed'
          ? 'failed' as const
          : 'idle' as const;
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
      client.connect(data.run, restoredStreamId);
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
