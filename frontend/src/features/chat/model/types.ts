export type {
  ChatMessage,
  ClarificationPrompt,
  ConversationSummary,
  ProactiveState,
  StructuredProgressStep,
  WorkspaceAction,
} from '../../../shared/types';

import type {
  ChatMessage,
  MakersMapPlace,
  MakersRouteMode,
  MakersRouteStrategy,
  ScheduleItem,
  WorkspaceAction,
} from '../../../shared/types';

export interface MakersChatRun {
  run_id?: string;
  status?: 'running' | 'cancel_requested' | 'completed' | 'failed' | 'cancelled';
  error?: string;
  diagnostics?: {
    stage?: string;
    category?: string;
    status_code?: number;
    request_id?: string;
    retryable?: boolean;
  };
  started_at?: number;
  updated_at?: number;
  completed_at?: number | null;
}

export interface BootstrapData {
  messages: ChatMessage[];
  schedules?: ScheduleItem[];
  map_places?: MakersMapPlace[];
  map_title?: string;
  map_route_mode?: MakersRouteMode | '';
  map_route_strategy?: MakersRouteStrategy | '';
  map_show_route?: boolean;
  workspace_revision?: number;
  workspace_actions?: WorkspaceAction[];
  run?: MakersChatRun | null;
}

export interface BootstrapOptions {
  signal?: AbortSignal;
  strict?: boolean;
  timeoutMs?: number;
}
