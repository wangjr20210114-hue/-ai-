import type { MakersRouteMode } from '../../maps/model';
import type {
  InstalledSkill,
  SkillConnectionState,
  UserSkillRecord,
} from '../../skills/model';

export interface ProactivePreferences {
  enabled: boolean;
  autonomy_mode: 'observe' | 'remind' | 'propose' | 'low_risk_auto';
  timezone: string;
  quiet_hours: { enabled: boolean; start: string; end: string };
  daily_limit: number;
  lookahead_hours: number;
  window_limit: number;
  provider_schedule_limit: number;
  route_gap_hours: number;
  travel_buffer_minutes: number;
  fallback_mottos: string[];
  types: Record<string, boolean>;
}

export interface ProactiveNotification {
  id: string;
  event_id: string;
  run_id: string;
  type: string;
  title: string;
  body: string;
  reason: string;
  action_prompt: string;
  priority: 'high' | 'normal' | 'low';
  evidence: Record<string, unknown>;
  status: 'unread' | 'read' | 'snoozed' | 'dismissed';
  version: number;
  snoozed_until?: number | null;
  read_at?: number | null;
  dismissed_at?: number | null;
  expires_at?: number | null;
  created_at: number;
  updated_at: number;
  window_origin?: 'memory' | 'operation';
}

export interface ProactiveRun {
  id: string;
  event_id: string;
  status: string;
  intent: string;
  trigger_origin: string;
  reason: string;
  created_at: number;
  updated_at: number;
}

export interface ProactiveWorkflow {
  id: string;
  title: string;
  reason: string;
  status: 'awaiting_confirmation' | 'active' | 'completed' | 'rejected' | 'cancelled';
  version: number;
  anchor_at?: number | null;
  steps: Array<{
    id: string;
    offset_minutes: number;
    title: string;
    body: string;
    action_prompt: string;
    depends_on?: string[];
    status: 'pending' | 'notified' | 'completed' | 'skipped' | 'failed' | 'attention_required' | 'compensating' | 'compensated';
    attempt?: number;
    last_error?: string;
    compensation?: { title: string; body: string; action_prompt: string } | null;
    due_at?: number | null;
    emitted_at?: number | null;
  }>;
  created_at: number;
  updated_at: number;
}

export interface ProactiveState {
  schema_version: number;
  revision: number;
  preferences: ProactivePreferences;
  notifications: ProactiveNotification[];
  runs: ProactiveRun[];
  workflows: ProactiveWorkflow[];
  checkpoints: Record<string, Record<string, unknown>>;
  last_tick?: { started_at: number; finished_at: number; stats: Record<string, number> } | null;
}

export interface MakersMemoryProposal {
  id: string;
  memory_key: string;
  value: unknown;
  reason: string;
  sensitivity: 'normal' | 'sensitive';
  status: 'pending' | 'confirmed' | 'rejected';
  version: number;
  created_at: number;
  updated_at: number;
}

export interface MakersMemory {
  id: string;
  memory_key: string;
  value: unknown;
  confidence: number;
  sensitivity: string;
  version: number;
  history?: Array<{ version: number; value: unknown; sensitivity: 'normal' | 'sensitive'; updated_at: number }>;
  created_at: number;
  updated_at: number;
}

export interface ProactiveRuleProposal {
  id: string;
  kind: string;
  target: string;
  reason: string;
  status: 'pending' | 'confirmed' | 'rejected';
  version: number;
  created_at: number;
  updated_at: number;
}

export interface MakersIntelligenceState {
  schema_version: number;
  revision: number;
  memory_proposals: MakersMemoryProposal[];
  memories: MakersMemory[];
  memory_count?: number;
  memory_preferences?: { enabled: boolean };
  search_preferences?: { result_limit: number; image_limit: number; parallel_image_search: boolean };
  map_preferences?: {
    service_mode: 'fast' | 'balanced' | 'complete';
    place_result_limit: number;
    route_stop_limit: number;
    search_timeout_seconds: number;
    preferred_route_mode: MakersRouteMode;
    route_strategy: 'time_then_cost' | 'least_time' | 'least_cost';
    near_time_tolerance_minutes: number;
    learn_route_preferences: boolean;
  };
  skill_preferences?: Record<string, boolean>;
  skill_catalog?: InstalledSkill[];
  skill_connections?: Record<string, SkillConnectionState>;
  user_skills?: UserSkillRecord[];
  providers?: Record<string, boolean>;
  rule_proposals: ProactiveRuleProposal[];
  feedback_count: number;
  usage: {
    daily_tokens: number;
    monthly_tokens: number;
    preferences: { daily_token_limit: number; monthly_token_limit: number; enforcement: 'off' | 'soft' | 'hard' };
    alerts: { daily: boolean; monthly: boolean };
  };
}

export interface ProviderBalance {
  currency: string;
  total_balance: string;
  granted_balance: string;
  topped_up_balance: string;
}

export interface ProviderUsageSummary {
  refreshed_at: number;
  usage: MakersIntelligenceState['usage'];
  metering: {
    daily: Record<string, number>;
    monthly: Record<string, number>;
    providers: Record<string, Record<string, number>>;
    recorded_events: number;
    timezone: string;
  };
  providers: Array<{
    id: 'deepseek' | string;
    configured: boolean;
    status: 'available' | 'unavailable' | 'credentials_required' | 'temporarily_unavailable';
    is_available: boolean;
    balances: ProviderBalance[];
    checked_at: number;
  }>;
}

export type { AuthSession, SessionIdentity } from '../../../shared/auth/session';
