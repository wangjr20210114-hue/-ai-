import type { ChatMessage, ConversationSummary, TravelPlan, ScheduleItem, StoredFileInfo, MakersMapPlace, MakersRoutePlan, WorkspaceAction, ProactiveState, MakersIntelligenceState } from '../types';

import { authorizedFetch, withEdgeOneAuth } from './auth';
import { createConversationId, makersConversationHeaders } from './conversation';
import { splitSseFrames } from './sse';
import { normalizeTimestamp } from './time';
import { isCurrentConversationId } from './dataVersion';
import { translate } from '../i18n';

export interface BootstrapData {
  messages: ChatMessage[];
  schedules?: ScheduleItem[];
  map_places?: MakersMapPlace[];
  map_title?: string;
  workspace_revision?: number;
  workspace_actions?: WorkspaceAction[];
  run?: MakersChatRun | null;
}

export interface MakersChatRun {
  run_id?: string;
  status?: 'running' | 'cancel_requested' | 'completed' | 'failed' | 'cancelled';
  error?: string;
  started_at?: number;
  updated_at?: number;
  completed_at?: number | null;
}

export interface WorkspaceResponse {
  revision: number;
  schedules: ScheduleItem[];
  map?: { action_id: string; title: string; places: MakersMapPlace[] } | null;
  action?: WorkspaceAction;
  actions?: WorkspaceAction[];
  changed?: Array<ScheduleItem & { deleted?: boolean }>;
  travel_plan?: TravelPlan;
  travel_plans?: TravelPlan[];
  deleted_plan_id?: string;
}

export type DataResetErrorCode = 'INVALID_PASSWORD' | 'RESET_NOT_CONFIGURED' | 'RESET_FAILED';

export class DataResetError extends Error {
  code: DataResetErrorCode;

  constructor(code: DataResetErrorCode) {
    super(code);
    this.name = 'DataResetError';
    this.code = code;
  }
}

function dataResetErrorCode(value: unknown): DataResetErrorCode {
  if (value === 'INVALID_PASSWORD' || value === 'RESET_NOT_CONFIGURED') return value;
  return 'RESET_FAILED';
}

export async function resetApplicationData(
  conversationId: string,
  password: string,
): Promise<{ conversations_deleted: number; state_items_deleted: number; files_deleted: number }> {
  const inspect = await authorizedFetch('/reset-files', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password, operation: 'inspect' }),
  });
  const inspectData = await inspect.json().catch(() => ({})) as {
    code?: string;
    conversation_ids?: string[];
  };
  if (!inspect.ok) throw new DataResetError(dataResetErrorCode(inspectData.code));

  const resetState = await authorizedFetch('/reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...makersConversationHeaders(conversationId) },
    body: JSON.stringify({
      password,
      conversation_ids: inspectData.conversation_ids || [],
    }),
  });
  const stateData = await resetState.json().catch(() => ({})) as {
    code?: string;
    state_items_deleted?: number;
  };
  if (!resetState.ok) throw new DataResetError(dataResetErrorCode(stateData.code));

  const resetFiles = await authorizedFetch('/reset-files', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password, operation: 'clear' }),
  });
  const fileData = await resetFiles.json().catch(() => ({})) as {
    code?: string;
    conversations_deleted?: number;
    deleted?: Record<string, number>;
  };
  if (!resetFiles.ok) throw new DataResetError(dataResetErrorCode(fileData.code));
  return {
    conversations_deleted: Number(fileData.conversations_deleted || 0),
    state_items_deleted: Number(stateData.state_items_deleted || 0),
    files_deleted: Object.values(fileData.deleted || {}).reduce((sum, value) => sum + Number(value || 0), 0),
  };
}

export async function workspaceOperation(
  conversationId: string,
  operation: string,
  input: Record<string, unknown> = {},
): Promise<WorkspaceResponse> {
  const res = await authorizedFetch('/workspace', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...makersConversationHeaders(conversationId) },
    body: JSON.stringify({ operation, ...input }),
  });
  const data = await res.json().catch(() => ({})) as WorkspaceResponse & { error?: string };
  if (!res.ok) throw new Error(data.error || translate('workspaceOperationFailed'));
  if (typeof window !== 'undefined' && Array.isArray(data.schedules)) {
    window.dispatchEvent(new CustomEvent('yuanbao:workspace-changed', { detail: data }));
    if (Array.isArray(data.changed) && data.changed.length > 0) {
      window.dispatchEvent(new CustomEvent('yuanbao:calendar-changed', { detail: data }));
    }
  }
  return data;
}

export async function proactiveOperation(
  conversationId: string,
  operation = 'get',
  input: Record<string, unknown> = {},
): Promise<ProactiveState> {
  const res = await authorizedFetch('/proactive', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...makersConversationHeaders(conversationId) },
    body: JSON.stringify({ operation, ...input }),
  });
  const data = await res.json().catch(() => ({})) as ProactiveState & { error?: string };
  if (!res.ok) throw new Error(data.error || translate('proactiveOperationFailed'));
  return data;
}

export async function intelligenceOperation(
  conversationId: string,
  operation = 'get',
  input: Record<string, unknown> = {},
): Promise<MakersIntelligenceState> {
  const res = await authorizedFetch('/intelligence', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...makersConversationHeaders(conversationId) },
    body: JSON.stringify({ operation, ...input }),
  });
  const data = await res.json().catch(() => ({})) as MakersIntelligenceState & { error?: string };
  if (!res.ok) throw new Error(data.error || translate('intelligenceOperationFailed'));
  return data;
}

export async function skillsOperation(
  conversationId: string,
  preferences?: Record<string, boolean>,
): Promise<{ preferences: Record<string, boolean>; providers: { meeting: boolean } }> {
  const intelligence = await intelligenceOperation(
    conversationId,
    preferences ? 'update_skill_preferences' : 'get',
    preferences ? { preferences } : {},
  );
  return {
    preferences: intelligence.skill_preferences || {},
    providers: { meeting: Boolean(intelligence.providers?.meeting) },
  };
}

export async function streamImageEdit(
  conversationId: string,
  prompt: string,
  parentActionId: string,
): Promise<WorkspaceAction> {
  const res = await authorizedFetch('/image', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...makersConversationHeaders(conversationId) },
    body: JSON.stringify({ prompt, parent_action_id: parentActionId }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({})) as { error?: string };
    throw new Error(data.error || translate('imageEditStatusFailed', { status: res.status }));
  }
  const reader = res.body?.getReader();
  if (!reader) throw new Error(translate('imageEditProgressReadFailed'));
  const decoder = new TextDecoder();
  let buffer = '';
  let action: WorkspaceAction | undefined;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parsed = splitSseFrames(buffer); buffer = parsed.rest;
    for (const frame of parsed.frames) {
      if (frame === '[DONE]') break;
      try {
        const event = JSON.parse(frame) as { type?: string; action?: WorkspaceAction; error?: string };
        if (event.type === 'image_action' && event.action) action = event.action;
      } catch { /* Heartbeats and malformed frames do not end the edit. */ }
    }
  }
  if (!action) throw new Error(translate('imageEditNoVersion'));
  return action;
}

export async function searchMakersPlaces(
  conversationId: string,
  query: string,
  city = '全国',
): Promise<MakersMapPlace[]> {
  const res = await authorizedFetch('/places', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...makersConversationHeaders(conversationId) },
    body: JSON.stringify({ query, city, limit: 10 }),
  });
  const data = await res.json().catch(() => ({})) as { places?: MakersMapPlace[]; error?: string };
  if (!res.ok) throw new Error(data.error || translate('placeSearchFailed'));
  return data.places || [];
}

export async function planMakersRoute(
  conversationId: string,
  places: MakersMapPlace[],
): Promise<MakersRoutePlan> {
  const res = await authorizedFetch('/routes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...makersConversationHeaders(conversationId) },
    // Callers supply an intentional itinerary order. Keep it unchanged so a
    // shortest-path optimization cannot contradict the calendar chronology.
    body: JSON.stringify({ places, mode: 'driving', optimize: false }),
  });
  const data = await res.json().catch(() => ({})) as { route?: MakersRoutePlan; error?: string };
  if (!res.ok || !data.route) throw new Error(data.error || translate('realRoutePlanningFailed'));
  return data.route;
}

export interface BootstrapOptions {
  signal?: AbortSignal;
  strict?: boolean;
  timeoutMs?: number;
}

export async function bootstrapApp(
  conversationId: string,
  options: BootstrapOptions = {},
): Promise<BootstrapData> {
  const controller = new AbortController();
  const abortFromCaller = () => controller.abort();
  options.signal?.addEventListener('abort', abortFromCaller, { once: true });
  const timeout = window.setTimeout(
    () => controller.abort(),
    Math.max(1000, options.timeoutMs ?? 8000),
  );
  try {
    const res = await authorizedFetch('/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...makersConversationHeaders(conversationId) },
      body: JSON.stringify({ conversation_id: conversationId }),
      signal: controller.signal,
    });
    if (res.ok) return res.json();
    if (options.strict) throw new Error(translate('makersRunReadStatusFailed', { status: res.status }));
  } catch (error) {
    if (options.strict) throw error;
    /* a new conversation has no checkpoint yet */
  } finally {
    window.clearTimeout(timeout);
    options.signal?.removeEventListener('abort', abortFromCaller);
  }
  return { messages: [] };
}

function normalizeConversation(item: Record<string, unknown>): ConversationSummary {
  const metadata = item.metadata && typeof item.metadata === 'object'
    ? item.metadata as Record<string, unknown>
    : {};
  const id = String(item.conversationId || item.id || '');
  const createdAt = normalizeTimestamp(item.createdAt ?? item.created_at);
  const updatedAt = normalizeTimestamp(item.lastMessageAt ?? item.updatedAt ?? item.updated_at, createdAt);
  const run = metadata.yuanbao_chat_run_v1 && typeof metadata.yuanbao_chat_run_v1 === 'object'
    ? metadata.yuanbao_chat_run_v1 as MakersChatRun
    : null;
  const activityStatus = run?.status === 'running' || run?.status === 'cancel_requested'
    ? 'running'
    : run?.status === 'failed' ? 'failed' : 'idle';
  return {
    id,
    title: String(metadata.title || item.title || translate('newConversation')),
    createdAt,
    updatedAt,
    messageCount: Number(item.messageCount || item.message_count || 0),
    activityStatus,
  };
}

export async function listConversations(): Promise<ConversationSummary[]> {
  const res = await authorizedFetch('/conversations');
  if (!res.ok) throw new Error(translate('readConversationsFailed'));
  const data = await res.json() as { conversations?: Record<string, unknown>[] };
  return (data.conversations || [])
    .map(normalizeConversation)
    .filter((item) => item.id && isCurrentConversationId(item.id))
    .sort((a, b) => b.updatedAt - a.updatedAt);
}

export async function createNewConversation(): Promise<ConversationSummary> {
  const now = Date.now();
  return { id: createConversationId(), title: translate('newConversation'), createdAt: now, updatedAt: now, messageCount: 0, pending: true };
}

export async function saveConversationMessage(conversationId: string, message: ChatMessage): Promise<void> {
  const res = await authorizedFetch('/conversation', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...makersConversationHeaders(conversationId) },
    body: JSON.stringify({
      role: message.role, content: message.content, metadata: message,
    }),
  });
  if (!res.ok) throw new Error(translate('saveMessageFailed'));
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('yuanbao:conversation-saved', {
      detail: { conversationId },
    }));
  }
}

export async function uploadDocument(conversationId: string, file: File): Promise<StoredFileInfo> {
  const signed = await authorizedFetch('/files', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conversation_id: conversationId, name: file.name, content_type: file.type || 'application/pdf', size: file.size }),
  });
  const upload = await signed.json().catch(() => ({})) as { url?: string; key?: string; content_url?: string; error?: string };
  if (!signed.ok || !upload.url || !upload.key) throw new Error(upload.error || translate('blobUploadUrlFailed'));
  const stored = await fetch(upload.url, { method: 'PUT', headers: { 'Content-Type': file.type || 'application/pdf' }, body: file });
  if (!stored.ok) throw new Error(translate('blobUploadFailed'));
  return {
    id: upload.key, original_name: file.name, mime_type: file.type || 'application/pdf', size_bytes: file.size,
    page_count: 0, total_chars: 0, preview: translate('blobSavedPreview'), created_at: Date.now(),
    storage_key: upload.key, content_url: upload.content_url ? withEdgeOneAuth(upload.content_url) : undefined,
  };
}
