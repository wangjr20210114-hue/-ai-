import {
  openChatTurn,
  touchConversationIndex,
} from '../model/client';
import type { MakersChatRun, RunPresentationSnapshot } from '../model';
import type { ChatQueueItem } from '../model';
import type { ChatSendResult } from '../../../services/chatClient';
import { splitSseFrames } from '../../../shared/transport/sseClient';
import { translate, type TranslationKey } from '../../../i18n';
import {
  browserLocationRequestContext,
  currentBrowserLocation,
  requestBrowserLocationForChat,
} from '../../../services/browserLocation';
import { normalizeProgressEvent } from '../../search/model/progressModel';
import {
  TurnControlClient,
  turnControlDelay,
} from './turnControl';

export const CLIENT_EVENT_TYPES = [
  'optimistic_user', 'clarification_submitted', 'stream_start', 'stream_delta',
  'stream_reset', 'stream_end', 'answer_complete', 'experience_hint',
  'turn_started', 'stop_requested', 'transport_recovering', 'recovery_snapshot',
  'stream_snapshot',
  'queue_changed',
  'search_status', 'progress_event', 'search_results',
  'search_media', 'paper_results', 'follow_ups', 'proactive_update',
  'map_action', 'calendar_action', 'side_effect_action',
  'clarification_action', 'error',
] as const;

export type ClientEventType = typeof CLIENT_EVENT_TYPES[number];
export type ClientEvent = {
  [Type in ClientEventType]: {
    type: Type;
    payload: Record<string, unknown>;
  }
}[ClientEventType];

const STREAM_IDLE_TIMEOUT_MS = 20_000;
export const CHAT_INITIAL_RESPONSE_TIMEOUT_MS = 55_000;
const TURN_QUEUE_PREFIX = 'floris:turn-queue:';
export const MAX_WAITING_TURNS = 5;

type TurnMessage = { type?: string; payload?: Record<string, unknown> };
type TurnQueueDisposition = 'consume' | 'retry' | 'retain';

function clientMessageId(message: TurnMessage): string {
  const direct = String(message.payload?.client_message_id || '');
  if (direct) return direct;
  const clientMessage = message.payload?.client_message;
  return clientMessage && typeof clientMessage === 'object'
    ? String((clientMessage as Record<string, unknown>).id || '')
    : '';
}

function clientMessageContent(message: TurnMessage): string {
  const value = message.payload?.client_message;
  if (value && typeof value === 'object') {
    return String((value as Record<string, unknown>).content || message.payload?.text || '');
  }
  return String(message.payload?.text || '');
}

function queueStorageKey(conversationId: string): string {
  return `${TURN_QUEUE_PREFIX}${conversationId}`;
}

function readTurnQueue(conversationId: string): TurnMessage[] {
  try {
    const value = JSON.parse(window.localStorage.getItem(queueStorageKey(conversationId)) || '[]');
    return Array.isArray(value) ? value.slice(0, 20) : [];
  } catch {
    return [];
  }
}

function recoverableTransportError(error: unknown, watchdogTriggered: boolean): boolean {
  const value = error as { name?: unknown; message?: unknown };
  return watchdogTriggered
    || ['AbortError', 'NetworkError', 'TypeError'].includes(String(value?.name || ''))
    || /failed to fetch|network|load failed/i.test(String(value?.message || ''));
}

export function canStartChatTransport(active: boolean): boolean {
  // Active conversations accept another message into their local FIFO.
  void active;
  return true;
}

export function locationRetryMessage(
  message: { type?: string; payload?: Record<string, unknown> },
) {
  const payload: Record<string, unknown> = {
    ...(message.payload || {}),
    _location_retry: true,
  };
  delete payload.client_message;
  return { type: message.type, payload };
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
  recommend_nearby_places_on_map: { active: 'toolNearbyPlacesActive', complete: 'toolNearbyPlacesComplete' },
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

export class SSEChatClient {
  private controller: AbortController | null = null;
  private listeners = new Set<(message: ClientEvent) => void>();
  private readonly turnControl: TurnControlClient;
  private pending: TurnMessage[];
  private ready = false;
  private closed = false;
  private draining = false;
  private explicitlyStoppedTurns = new Set<string>();
  private activeClientMessageId = '';
  private activeStreamId = '';
  private startedTurns = new Set<string>();

  constructor(private readonly conversationId: string) {
    this.turnControl = new TurnControlClient(conversationId);
    this.pending = readTurnQueue(conversationId);
  }

  private persistQueue() {
    try {
      if (this.pending.length) {
        window.localStorage.setItem(
          queueStorageKey(this.conversationId),
          JSON.stringify(this.pending.slice(0, 20)),
        );
      } else {
        window.localStorage.removeItem(queueStorageKey(this.conversationId));
      }
    } catch {
      // The in-memory FIFO remains valid when storage is full or unavailable.
      try {
        window.localStorage.removeItem(queueStorageKey(this.conversationId));
      } catch {
        // Storage is entirely unavailable; keep only the in-memory queue.
      }
    }
    this.emitQueue();
  }

  private waitingMessages(): TurnMessage[] {
    if (!this.pending.length) return [];
    if (this.activeClientMessageId) {
      const activeIndex = this.pending.findIndex(
        (message) => clientMessageId(message) === this.activeClientMessageId,
      );
      return activeIndex < 0
        ? [...this.pending]
        : this.pending.filter((_message, index) => index !== activeIndex);
    }
    return this.pending.slice(1);
  }

  queuedTurns(): ChatQueueItem[] {
    return this.waitingMessages().map((message) => ({
      id: clientMessageId(message),
      content: clientMessageContent(message),
      enqueuedAt: Number(message.payload?.client_message && typeof message.payload.client_message === 'object'
        ? (message.payload.client_message as Record<string, unknown>).ts
        : 0) || Date.now(),
    })).filter((item) => item.id && item.content);
  }

  private emitQueue() {
    this.emit({ type: 'queue_changed', payload: { items: this.queuedTurns() } });
  }

  private consumeQueuedTurn(clientId: string): boolean {
    const normalized = String(clientId || '');
    if (!normalized) return false;
    const index = this.pending.findIndex(
      (message) => clientMessageId(message) === normalized,
    );
    if (index < 0) return false;
    this.pending.splice(index, 1);
    this.persistQueue();
    return true;
  }

  private emit(message: ClientEvent) {
    for (const listener of this.listeners) listener(message);
  }

  private emitOptimisticUser(message: TurnMessage): void {
    const id = clientMessageId(message);
    const value = message.payload?.client_message;
    if (
      !id
      || !value
      || typeof value !== 'object'
      || this.startedTurns.has(id)
    ) return;
    this.startedTurns.add(id);
    this.emit({
      type: 'optimistic_user',
      payload: {
        message: {
          ...value,
          id,
          client_message_id: id,
          queued: false,
        },
      },
    });
  }

  on(listener: (message: ClientEvent) => void) {
    this.listeners.add(listener);
    listener({ type: 'queue_changed', payload: { items: this.queuedTurns() } });
    return () => this.listeners.delete(listener);
  }

  updateQueuedTurn(clientId: string, content: string): boolean {
    const normalized = content.trim();
    const waiting = new Set(this.waitingMessages());
    const message = this.pending.find((item) => (
      clientMessageId(item) === clientId && waiting.has(item)
    ));
    if (!message || !normalized) return false;
    const clientMessage = message.payload?.client_message;
    message.payload = {
      ...(message.payload || {}),
      text: normalized,
      ...(clientMessage && typeof clientMessage === 'object'
        ? { client_message: { ...clientMessage, content: normalized } }
        : {}),
    };
    this.persistQueue();
    return true;
  }

  removeQueuedTurn(clientId: string): boolean {
    const waiting = new Set(this.waitingMessages());
    const index = this.pending.findIndex((item) => (
      clientMessageId(item) === clientId && waiting.has(item)
    ));
    if (index < 0) return false;
    this.pending.splice(index, 1);
    this.persistQueue();
    return true;
  }

  async interruptWithQueuedTurn(clientId: string): Promise<'confirmed' | 'local' | 'started'> {
    const waiting = new Set(this.waitingMessages());
    const index = this.pending.findIndex((item) => (
      clientMessageId(item) === clientId && waiting.has(item)
    ));
    if (index < 0) return 'local';
    const [selected] = this.pending.splice(index, 1);
    const activeIndex = this.activeClientMessageId
      ? this.pending.findIndex((item) => clientMessageId(item) === this.activeClientMessageId)
      : -1;
    this.pending.splice(activeIndex >= 0 ? activeIndex + 1 : 0, 0, selected);
    this.persistQueue();
    if (this.activeClientMessageId) return this.stop();
    void this.drain();
    return 'started';
  }

  connect(run?: MakersChatRun | null, restoredStreamId = '') {
    this.closed = false;
    this.ready = true;
    if (this.turnControl.hasStopIntent && (this.turnControl.stopClientMessageId || run)) {
      const stoppedClientMessageId = (
        this.turnControl.stopClientMessageId || String(run?.client_message_id || '')
      );
      this.activeClientMessageId = stoppedClientMessageId;
      this.activeStreamId = restoredStreamId || `ai-recover-${run?.run_id || Date.now()}`;
      this.emit({
        type: 'stop_requested',
        payload: {
          id: this.activeStreamId,
          client_message_id: this.activeClientMessageId,
        },
      });
      const newerRunActive = Boolean(
        (run?.status === 'running' || run?.status === 'cancel_requested')
        && run.client_message_id
        && run.client_message_id !== stoppedClientMessageId
      );
      void this.cancelMakerRun(
        stoppedClientMessageId,
        newerRunActive
          ? () => {
              this.activeClientMessageId = String(run?.client_message_id || '');
              this.activeStreamId = restoredStreamId || `ai-recover-${run?.run_id || Date.now()}`;
              void this.recoverExistingRun(
                this.activeClientMessageId,
                this.activeStreamId,
              );
            }
          : undefined,
      );
      return;
    }
    if (
      run?.client_message_id
      && ['completed', 'cancelled', 'failed'].includes(String(run.status || ''))
    ) {
      this.consumeQueuedTurn(String(run.client_message_id));
    }
    if (
      !this.controller
      && (run?.status === 'running' || run?.status === 'cancel_requested')
    ) {
      this.activeClientMessageId = String(run.client_message_id || '');
      this.activeStreamId = restoredStreamId || `ai-recover-${run.run_id || Date.now()}`;
      void this.recoverExistingRun(this.activeClientMessageId, this.activeStreamId);
      return;
    }
    void this.drain();
  }

  hasActiveTransport(): boolean {
    return Boolean(this.controller);
  }

  private cancellationConfirmed(clientId: string, onConfirmed?: () => void) {
    this.consumeQueuedTurn(clientId);
    if (this.activeClientMessageId === clientId) {
      this.activeClientMessageId = '';
      this.activeStreamId = '';
    }
    if (onConfirmed) onConfirmed();
    else void this.drain();
  }

  private async cancelMakerRun(
    clientId: string,
    onConfirmed?: () => void,
  ): Promise<'confirmed' | 'local'> {
    const outcome = await this.turnControl.stop(
      clientId,
      () => this.cancellationConfirmed(clientId, onConfirmed),
    );
    return outcome;
  }

  async stop(): Promise<'confirmed' | 'local'> {
    // Record intent before aborting the transport. The durable local marker is
    // cleared only after the server confirms its cancellation tombstone.
    this.explicitlyStoppedTurns.add(this.activeClientMessageId);
    this.turnControl.markStopped(this.activeClientMessageId);
    this.controller?.abort();
    this.emit({
      type: 'stop_requested',
      payload: {
        id: this.activeStreamId,
        client_message_id: this.activeClientMessageId,
      },
    });
    return this.cancelMakerRun(this.activeClientMessageId);
  }

  async send(rawMessage: unknown): Promise<ChatSendResult> {
    if (this.closed) return 'ignored';
    const message = rawMessage as TurnMessage;
    if (message.type === 'ping') return 'ignored';
    const queued = Boolean(this.controller || this.draining || this.pending.length);
    if (queued && this.queuedTurns().length >= MAX_WAITING_TURNS) return 'queue_full';
    this.pending.push(message);
    this.persistQueue();
    // Receipt and execution are separate boundaries. The runnable FIFO head
    // is visible immediately even while a new conversation is still loading;
    // later waiting turns remain only in the editable queue drawer.
    if (!queued) this.emitOptimisticUser(message);
    void this.drain();
    return queued ? 'queued' : 'started';
  }

  private async drain() {
    if (!this.ready || this.closed || this.draining) return;
    this.draining = true;
    try {
      while (this.ready && this.pending.length) {
        // Messages remain accepted into the FIFO, but no successor reaches
        // the server until the exact prior stop tombstone is confirmed.
        if (this.turnControl.hasStopIntent) break;
        const message = this.pending[0];
        if (!message) break;
        const disposition = await this.runTurn(message);
        if (disposition === 'consume' && this.pending[0] === message) {
          this.pending.shift();
          this.persistQueue();
        }
        if (disposition === 'retain') break;
      }
    } finally {
      this.draining = false;
    }
  }

  private async recoverActiveRun(
    expectedClientMessageId: string,
    streamId: string,
  ): Promise<'completed' | 'cancelled' | 'failed' | 'not_admitted'> {
    const recoveryController = new AbortController();
    this.controller = recoveryController;
    this.emit({
      type: 'transport_recovering',
      payload: { id: streamId },
    });
    let recoveredRevision = -1;
    const recovery = await this.turnControl.recover(
      expectedClientMessageId,
      recoveryController.signal,
      (state) => {
        const snapshot = state.presentation as RunPresentationSnapshot | null | undefined;
        const revision = Number(snapshot?.revision || 0);
        if (
          !snapshot
          || snapshot.client_message_id !== expectedClientMessageId
          || revision <= recoveredRevision
        ) return;
        recoveredRevision = revision;
        this.emit({
          type: 'stream_snapshot',
          payload: {
            id: streamId,
            snapshot: {
              ...snapshot,
              progress: (snapshot.progress || [])
                .map((item) => normalizeProgressEvent(item))
                .filter(Boolean),
            },
          },
        });
      },
    );
    if (recovery.outcome === 'completed' && recovery.data) {
      this.emit({
        type: 'recovery_snapshot',
        payload: { id: streamId, data: recovery.data },
      });
    } else if (recovery.outcome === 'cancelled') {
      this.emit({
        type: 'stop_requested',
        payload: { id: streamId, client_message_id: expectedClientMessageId },
      });
    } else if (recovery.outcome === 'failed') {
      this.emit({
        type: 'error',
        payload: {
          id: streamId,
          message: String(
            recovery.run?.error || translate('generationFailedRetry')
          ),
        },
      });
    }
    return recovery.outcome;
  }

  private async recoverExistingRun(clientId: string, streamId: string) {
    try {
      const outcome = await this.recoverActiveRun(clientId, streamId);
      if (outcome !== 'not_admitted') this.consumeQueuedTurn(clientId);
    } finally {
      this.emit({ type: 'stream_end', payload: { id: streamId } });
      this.controller = null;
      this.activeClientMessageId = '';
      this.activeStreamId = '';
      void this.drain();
    }
  }

  private async runTurn(message: TurnMessage): Promise<TurnQueueDisposition> {
    const currentClientMessageId = clientMessageId(message);
    this.controller = new AbortController();
    const signal = this.controller.signal;
    const streamId = `ai-stream-${Date.now()}-${currentClientMessageId || 'turn'}`;
    this.activeClientMessageId = currentClientMessageId;
    this.activeStreamId = streamId;
    let streamFinished = false;
    let protocolDone = false;
    let idleWatchdog: number | undefined;
    let watchdogTriggered = false;
    let locationRetryRequested = false;
    const armWatchdog = (timeoutMs = STREAM_IDLE_TIMEOUT_MS) => {
      if (idleWatchdog) window.clearTimeout(idleWatchdog);
      idleWatchdog = window.setTimeout(() => {
        watchdogTriggered = true;
        this.controller?.abort();
      }, timeoutMs);
    };

    const clientMessage = message.payload?.client_message;
    const clientMessageTitle = clientMessage && typeof clientMessage === 'object'
      && typeof (clientMessage as Record<string, unknown>).content === 'string'
      ? String((clientMessage as Record<string, unknown>).content)
      : '';
    if (clientMessage && typeof clientMessage === 'object') {
      this.emitOptimisticUser(message);
    }
    this.emit({
      type: 'turn_started',
      payload: { client_message_id: currentClientMessageId },
    });
    const clarificationResponse = message.payload?.clarification_response;
    if (clarificationResponse && typeof clarificationResponse === 'object') {
      const sourceMessageId = String(
        (clarificationResponse as Record<string, unknown>).source_message_id || '',
      );
      if (sourceMessageId) {
        this.emit({
          type: 'clarification_submitted',
          payload: { message_id: sourceMessageId },
        });
      }
    }

    const finish = () => {
      if (streamFinished) return;
      streamFinished = true;
      this.emit({ type: 'stream_end', payload: { id: streamId } });
    };

    this.emit({
      type: 'stream_start',
      payload: { id: streamId, intent: 'chat', client_message_id: currentClientMessageId },
    });

    try {
      // Semantic planning and the runtime Skill gate run before the HTTP body
      // starts streaming. Give that first response a bounded window matching
      // the product's one-minute ceiling; once headers/data arrive, return to
      // the shorter idle watchdog so a stalled stream still stops quickly.
      armWatchdog(CHAT_INITIAL_RESPONSE_TIMEOUT_MS);
      const browserLocation = currentBrowserLocation();
      const locationRequest = browserLocationRequestContext();
      const response = await openChatTurn(
        this.conversationId,
        {
          ...(message.payload || {}),
          ...(browserLocation ? { current_location: browserLocation } : {}),
          location_request: locationRequest,
        },
        signal,
      );

      // A stop can race the server's admission boundary. Even if that request
      // has already produced an HTTP response, deliberate cancellation stays
      // silent and must never be interpreted as a retryable busy response.
      if (
        this.turnControl.isStopped(currentClientMessageId)
        || this.explicitlyStoppedTurns.has(currentClientMessageId)
      ) {
        finish();
        return 'consume';
      }

      if (!response.ok) {
        if (response.status === 409) {
          finish();
          await turnControlDelay(2_000, signal);
          return 'retry';
        }
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
            void touchConversationIndex(this.conversationId, clientMessageTitle, 2).catch(() => {});
            finish();
            return 'consume';
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
                    toolName,
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
                    toolName: String(event.name || ''),
                    status: 'analyzing',
                    statusText: progressTextForTool(String(event.name || ''), 'complete'),
                  },
                });
                break;
              case 'progress_event': {
                const step = normalizeProgressEvent(event.payload);
                if (step) {
                  this.emit({
                    type: 'progress_event',
                    payload: { id: streamId, step },
                  });
                }
                break;
              }
              case 'map_action':
              case 'calendar_action':
              case 'side_effect_action':
                this.emit({
                  type: String(event.type) as 'map_action' | 'calendar_action' | 'side_effect_action',
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
              case 'browser_location_request':
                await requestBrowserLocationForChat();
                locationRetryRequested = true;
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
                  payload: {
                    id: streamId,
                    toolName: 'rich_search',
                    status: 'arranging',
                    statusText: translate('arrangingReviewedImages'),
                  },
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
              case 'experience_hint': {
                const payload = event.payload && typeof event.payload === 'object'
                  ? event.payload as Record<string, unknown>
                  : {};
                this.emit({
                  type: 'experience_hint',
                  payload: {
                    id: streamId,
                    items: Array.isArray(payload.items) ? payload.items : [],
                  },
                });
                break;
              }
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
      // A bare EOF means the connection disappeared. Recover the same Maker
      // run from its checkpoint; never start a duplicate model request.
      if (!protocolDone) {
        const disconnected = new Error(translate('networkGenerationEnded'));
        disconnected.name = 'NetworkError';
        throw disconnected;
      }
      finish();
    } catch (error) {
      let disposition: TurnQueueDisposition = 'consume';
      const explicitlyStopped = this.explicitlyStoppedTurns.has(currentClientMessageId);
      if (this.closed && !explicitlyStopped) {
        // A route change or refresh only detaches the browser transport. Keep
        // the exact FIFO head until bootstrap reports the Maker run terminal.
        disposition = 'retain';
      } else if (!explicitlyStopped && recoverableTransportError(error, watchdogTriggered)) {
        const outcome = await this.recoverActiveRun(currentClientMessageId, streamId);
        if (outcome === 'not_admitted') {
          disposition = 'retry';
          await turnControlDelay(2_000, signal);
        }
      } else if (!this.closed && !explicitlyStopped) {
        this.emit({
          type: 'error',
          payload: { id: streamId, message: terminalGenerationError(error, watchdogTriggered) },
        });
      }
      finish();
      return disposition;
    } finally {
      if (idleWatchdog) window.clearTimeout(idleWatchdog);
      this.controller = null;
      this.explicitlyStoppedTurns.delete(currentClientMessageId);
      this.activeClientMessageId = '';
      this.activeStreamId = '';
      if (
        locationRetryRequested
        && !this.turnControl.isStopped(currentClientMessageId)
      ) {
        void this.send(locationRetryMessage(message));
      }
    }
    return 'consume';
  }

  close() {
    // Unmount/refresh only detaches this page. Explicit user cancellation is
    // handled by stop(); never turn a browser refresh into a server-side stop.
    this.controller?.abort();
    this.controller = null;
    this.ready = false;
    this.closed = true;
    this.turnControl.close();
  }
}
