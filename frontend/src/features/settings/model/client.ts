import { requestJson } from '../../../shared/transport/httpClient';
import { authorizedFetch } from '../../../shared/auth/session';
import type {
  MakersIntelligenceState,
  ProactiveState,
  ProviderUsageSummary,
} from './types';


export const routes = Object.freeze([
  '/auth/session',
  '/intelligence',
  '/proactive',
  '/provider_usage',
  '/reset',
  '/reset-files',
]);

export function loadSettingsSession<T>(): Promise<T> {
  return requestJson<T>('/auth/session');
}

export function loadProviderUsage<T>(conversationId: string): Promise<T> {
  return requestJson<T>('/provider_usage', {
    headers: { 'makers-conversation-id': conversationId },
  });
}

export function resetSettingsData<T>(
  conversationId: string,
  confirmation: string,
): Promise<T> {
  return requestJson<T>('/reset', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'makers-conversation-id': conversationId,
    },
    body: JSON.stringify({ confirmation }),
  });
}

export function proactiveOperation(
  conversationId: string,
  operation = 'get',
  input: Record<string, unknown> = {},
): Promise<ProactiveState> {
  return requestJson<ProactiveState>('/proactive', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'makers-conversation-id': conversationId,
    },
    body: JSON.stringify({ operation, ...input }),
  });
}

export function intelligenceOperation(
  conversationId: string,
  operation = 'get',
  input: Record<string, unknown> = {},
): Promise<MakersIntelligenceState> {
  return requestJson<MakersIntelligenceState>('/intelligence', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'makers-conversation-id': conversationId,
    },
    body: JSON.stringify({ operation, ...input }),
  });
}

export async function getProviderUsage(
  conversationId: string,
): Promise<ProviderUsageSummary> {
  const data = await loadProviderUsage<ProviderUsageSummary>(conversationId);
  if (
    !data.usage
    || typeof data.usage.daily_tokens !== 'number'
    || typeof data.usage.monthly_tokens !== 'number'
    || !data.metering?.daily
    || !data.metering?.monthly
    || !Array.isArray(data.providers)
  ) {
    throw new Error('Provider usage response is invalid');
  }
  return data;
}

export type DataResetErrorCode =
  | 'INVALID_CONFIRMATION'
  | 'RESET_NOT_CONFIGURED'
  | 'RESET_FAILED';

export class DataResetError extends Error {
  code: DataResetErrorCode;

  constructor(code: DataResetErrorCode) {
    super(code);
    this.name = 'DataResetError';
    this.code = code;
  }
}

function dataResetErrorCode(value: unknown): DataResetErrorCode {
  if (value === 'INVALID_CONFIRMATION' || value === 'RESET_NOT_CONFIGURED') {
    return value;
  }
  return 'RESET_FAILED';
}

export async function resetApplicationData(
  conversationId: string,
  confirmation: string,
): Promise<{
  conversations_deleted: number;
  state_items_deleted: number;
  files_deleted: number;
}> {
  const inspect = await authorizedFetch('/reset-files', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ confirmation, operation: 'inspect' }),
  });
  const inspectData = await inspect.json().catch(() => ({})) as {
    code?: string;
    conversation_ids?: string[];
  };
  if (!inspect.ok) throw new DataResetError(dataResetErrorCode(inspectData.code));

  const resetState = await authorizedFetch('/reset', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'makers-conversation-id': conversationId,
    },
    body: JSON.stringify({
      confirmation,
      conversation_ids: inspectData.conversation_ids || [],
    }),
  });
  const stateData = await resetState.json().catch(() => ({})) as {
    code?: string;
    state_items_deleted?: number;
  };
  if (!resetState.ok) {
    throw new DataResetError(dataResetErrorCode(stateData.code));
  }

  const resetFiles = await authorizedFetch('/reset-files', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ confirmation, operation: 'clear' }),
  });
  const fileData = await resetFiles.json().catch(() => ({})) as {
    code?: string;
    conversations_deleted?: number;
    deleted?: Record<string, number>;
  };
  if (!resetFiles.ok) {
    throw new DataResetError(dataResetErrorCode(fileData.code));
  }
  return {
    conversations_deleted: Number(fileData.conversations_deleted || 0),
    state_items_deleted: Number(stateData.state_items_deleted || 0),
    files_deleted: Object.values(fileData.deleted || {}).reduce(
      (sum, value) => sum + Number(value || 0),
      0,
    ),
  };
}
