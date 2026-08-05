import type { ScheduleItem } from '../../calendar/model';
import type { MakersMapPlace, MakersRouteMode, MakersRouteStrategy } from '../../maps/model';
import type { PaperInfo, StoredFileInfo } from '../../papers/model';
import type { SearchMeta } from '../../search/model';
import type { ProactiveState } from '../../settings/model';
import type { WorkspaceAction } from '../../workspace/model';

export interface ConversationSummary {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messageCount: number;
  pending?: boolean;
  activityStatus?: 'idle' | 'running' | 'failed';
}

export interface DocumentContext {
  fileId: string;
  filename: string;
  text: string;
}

export interface SkillParams {
  message?: string;
  prompt?: string;
  user_message?: string;
  destination?: string;
  [key: string]: unknown;
}

export interface SkillInfo {
  intent: string;
  mode: string;
  content: string;
  icon: string;
  action_label: string;
  params: SkillParams;
  data: Record<string, unknown>;
}

export type StructuredProgressStage =
  | 'planning'
  | 'retrieval'
  | 'verification'
  | 'synthesis'
  | 'finalizing'
  | 'complete';

export type StructuredProgressActivity =
  | 'general'
  | 'web_search'
  | 'paper_search'
  | 'place_search'
  | 'route_planning'
  | 'calendar_preparation'
  | 'meeting_preparation'
  | 'image_generation'
  | 'image_review'
  | 'component_action';

export interface StructuredProgressStep {
  schema_version: 1;
  stage: StructuredProgressStage;
  status: 'active' | 'completed' | 'skipped';
  activity: StructuredProgressActivity;
  source: 'controller' | 'client';
  updated_at: number;
}

export interface ExperienceHint {
  kind: 'freshness' | 'skill_suggestion';
  skill_ids: string[];
  login_required?: boolean;
}

export type ClarificationFieldType = 'single' | 'multi' | 'boolean' | 'text' | 'date' | 'time' | 'datetime';

export interface ClarificationField {
  id: string;
  label: string;
  type: ClarificationFieldType;
  options?: string[];
  option_values?: Record<string, string>;
  required?: boolean;
  placeholder?: string;
}

export interface ClarificationPrompt {
  id: string;
  title: string;
  prompt: string;
  fields: ClarificationField[];
}

export interface ChatMessage {
  id: string;
  client_message_id?: string;
  role: 'user' | 'ai';
  content: string;
  ts: number;
  streaming?: boolean;
  queued?: boolean;
  stopped?: boolean;
  turnStartedAt?: number;
  searchStartedAt?: number;
  searchCompletedAt?: number;
  failed?: boolean;
  proactive?: boolean;
  followUps?: string[];
  progress?: StructuredProgressStep[];
  skill?: SkillInfo;
  papers?: PaperInfo[];
  paperFileId?: string;
  paperFileName?: string;
  paperTitle?: string;
  paperIsPaper?: boolean;
  searchResults?: SearchMeta;
  workspaceActions?: WorkspaceAction[];
  clarification?: ClarificationPrompt;
  clarificationAnswered?: boolean;
  experienceHints?: ExperienceHint[];
}

export interface ChatQueueItem {
  id: string;
  content: string;
  enqueuedAt: number;
}

export interface WSPayload {
  id?: string;
  session_id?: string;
  user_id?: string;
  conversation_id?: string;
  content?: string;
  delta?: string;
  error_type?: string;
  follow_ups?: string[];
  image_prompt?: string;
  image_url?: string;
  intent?: string;
  message?: string;
  mode?: string;
  icon?: string;
  action_label?: string;
  params?: SkillParams;
  data?: Record<string, unknown>;
  papers?: PaperInfo[];
  search_results?: SearchMeta;
  status?: string;
  activity?: string;
  text?: string;
  [key: string]: unknown;
}

export interface WSMessage {
  type:
    | 'user_activity'
    | 'suggestion'
    | 'chat_reply'
    | 'chat_thinking'
    | 'stream_start'
    | 'stream_delta'
    | 'stream_end'
    | 'search_status'
    | 'error'
    | 'ack'
    | 'ping'
    | 'pong';
  payload: WSPayload;
  ts?: number;
}

export interface MeetingResult {
  ok: boolean;
  need_auth?: boolean;
  meeting_id?: string;
  meeting_code?: string;
  join_url?: string;
  subject?: string;
  start_time?: string;
  error?: string;
}

export type {
  MakersMapPlace,
  MakersRouteMode,
  MakersRouteStrategy,
  PaperInfo,
  ProactiveState,
  ScheduleItem,
  SearchMeta,
  StoredFileInfo,
  WorkspaceAction,
};

export interface MakersChatRun {
  run_id?: string;
  client_message_id?: string;
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

export interface RunPresentationSnapshot {
  schema_version: 1;
  run_id: string;
  client_message_id: string;
  revision: number;
  updated_at: number;
  content: string;
  progress?: Record<string, unknown>[];
  search_results?: Partial<SearchMeta>;
  search_media?: Partial<SearchMeta>;
  workspace_actions?: WorkspaceAction[];
  clarification?: ClarificationPrompt;
  papers?: { papers?: PaperInfo[] };
  follow_ups?: string[];
  experience_hints?: ExperienceHint[];
  error?: string;
}

export interface ChatRunState {
  run?: MakersChatRun | null;
  presentation?: RunPresentationSnapshot | null;
}

export interface BootstrapData {
  messages: ChatMessage[];
  schedules?: ScheduleItem[];
  map_places?: MakersMapPlace[];
  map_title?: string;
  map_route_mode?: MakersRouteMode | '';
  map_route_strategy?: MakersRouteStrategy | '';
  map_route?: import('../../maps/model').MakersRoutePlan;
  map_show_route?: boolean;
  workspace_revision?: number;
  workspace_actions?: WorkspaceAction[];
  run?: MakersChatRun | null;
  presentation?: RunPresentationSnapshot | null;
}

export interface BootstrapOptions {
  signal?: AbortSignal;
  strict?: boolean;
  timeoutMs?: number;
}
