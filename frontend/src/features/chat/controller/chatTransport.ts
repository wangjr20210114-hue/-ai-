import {
  openChatTurn,
  requestConversationStop,
  touchConversationIndex,
} from '../model/client';
import { splitSseFrames } from '../../../shared/transport/sseClient';
import { translate, type TranslationKey } from '../../../i18n';
import {
  browserLocationRequestContext,
  currentBrowserLocation,
  requestBrowserLocationForChat,
} from '../../../services/browserLocation';
import { normalizeProgressEvent } from '../../search/model/progressModel';

export const CLIENT_EVENT_TYPES = [
  'optimistic_user', 'clarification_submitted', 'stream_start', 'stream_delta',
  'stream_reset', 'stream_end', 'answer_complete', 'experience_hint',
  'stop_requested', 'search_status', 'progress_event', 'search_results',
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
const STOP_TIMEOUT_MS = 4_000;
const MANUAL_STOP_PREFIX = 'floris:manual-stop:';

export function canStartChatTransport(active: boolean): boolean {
  return !active;
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
    const requestStop = (signal?: AbortSignal) => (
      requestConversationStop(this.conversationId, signal)
    );
    try {
      const response = await requestStop(stopController.signal);
      if (!response.ok) throw new Error(translate('streamRequestFailed', { status: response.status }));
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
    // A second click, Enter key event, clarification submit, or retry must
    // never abort and replace the request that currently owns this
    // conversation. The UI has its own disabled state, but this transport
    // guard closes the React render-window race as well.
    if (!canStartChatTransport(Boolean(this.controller))) return;

    // A deliberate new message is the only action that clears a manual stop.
    // Do not call stop() here because that would persist a false user intent.
    const allowAfterStop = this.manualStopIntent;
    this.setManualStopIntent(false);
    this.controller = new AbortController();
    const signal = this.controller.signal;
    const streamId = `ai-stream-${Date.now()}`;
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
      this.emit({ type: 'optimistic_user', payload: { message: clientMessage } });
    }
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

    this.emit({ type: 'stream_start', payload: { id: streamId, intent: 'chat' } });

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
          ...(allowAfterStop ? { _allow_after_stop: true } : {}),
        },
        signal,
      );

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
            void touchConversationIndex(this.conversationId, clientMessageTitle, 2).catch(() => {});
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
      if (locationRetryRequested && !this.manualStopIntent) {
        void this.send(locationRetryMessage(message));
      }
    }
  }

  close() {
    // Unmount/refresh only detaches this page. Explicit user cancellation is
    // handled by stop(); never turn a browser refresh into a server-side stop.
    this.controller?.abort();
    this.controller = null;
  }
}
