// 全局类型定义

export type ThemeMode = 'light' | 'dark';

export interface ConversationSummary {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messageCount: number;
  pending?: boolean;
  activityStatus?: 'idle' | 'running' | 'failed';
}

export interface ProactivePreferences {
  enabled: boolean;
  autonomy_mode: 'observe' | 'remind' | 'propose' | 'low_risk_auto';
  timezone: string;
  quiet_hours: { enabled: boolean; start: string; end: string };
  daily_limit: number;
  lookahead_hours: number;
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
  proactive_message?: ChatMessage | null;
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
  skill_preferences?: Record<string, boolean>;
  rule_proposals: ProactiveRuleProposal[];
  feedback_count: number;
  usage: {
    daily_tokens: number;
    monthly_tokens: number;
    preferences: { daily_token_limit: number; monthly_token_limit: number; enforcement: 'off' | 'soft' | 'hard' };
    alerts: { daily: boolean; monthly: boolean };
  };
}

export interface SkillParams {
  message?: string;
  prompt?: string;
  user_message?: string;
  destination?: string;
  [key: string]: unknown;
}

export interface TravelCollected {
  destination?: string;
  departure?: string;
  start_date?: string;
  end_date?: string;
  days?: number | string;
  travel_style?: string;
  scenery_preference?: string;
  [key: string]: string | number | undefined;
}

// ============ 技能结果（通用） ============
export interface SkillInfo {
  intent: string;       // "travel", "meeting", "news", "image", "translation", "paper", "chat"
  mode: string;         // "auto" | "suggest" | "immediate"
  content: string;      // Markdown 文本
  icon: string;          // emoji
  action_label: string;  // 按钮文案
  params: SkillParams;
  data: Record<string, unknown>;
}

export interface PaperInfo {
  title: string;
  arxiv_id: string;
  authors: string;
  year: number;
  abstract_zh: string;
  key_contribution: string;
  citations: string;
  arxiv_url: string;
  pdf_url: string;
}

// ============ 搜索结果 ============
export interface SearchResultItem {
  id: string;
  source: string;           // "web" | "wechat" | "zhihu" | "baike" | "wsa"
  title: string;
  snippet: string;
  url: string;
  account_name?: string;    // 微信公众号名
  gh_id?: string;           // 公众号原始ID
  avatar?: string;          // 公众号头像URL
  image?: string;           // 百科图片等
  date?: string;
}

export interface RichMediaAsset {
  id: string;
  kind: 'image' | 'generated_image' | string;
  url: string;
  source_id?: string;
  source_url?: string;
  source_title?: string;
  alt: string;
  caption: string;
  attribution?: string;
  generated: boolean;
}

export interface SearchMeta {
  schema_version?: number;
  query: string;
  results: SearchResultItem[];
  images: string[];
  media: RichMediaAsset[];
  sources_used: string[];
  total: number;
  target_date?: string;
  strict_date?: boolean;
  media_pending?: boolean;
  vision_diagnostics?: Record<string, number>;
  timings_ms?: Record<string, number>;
  cache_hit?: boolean;
  search_config?: {
    result_limit: number;
    image_limit: number;
    parallel_image_search: boolean;
    provider_request_count: number;
    page_fetch_limit: number;
  };
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'ai';
  content: string;
  ts: number;
  streaming?: boolean;      // 是否正在流式输出
  failed?: boolean;         // 瞬时失败提示；不写入本地缓存或 Makers 历史
  proactive?: boolean;      // 主动服务在空白新对话中生成的持久开场消息
  followUps?: string[];

  // 通用技能数据
  skill?: SkillInfo;

  // 旅游计划结果数据
  travelPlanData?: TravelPlan;
  travelStartTs?: number;
  parsedSchedules?: Partial<ScheduleItem>[];

  // 论文数据
  papers?: PaperInfo[];
  paperFileId?: string;
  paperFileName?: string;
  paperTitle?: string;
  showPaperReader?: boolean;

  // 搜索结果数据
  searchResults?: SearchMeta;

  // 兼容旧字段
  travelIntent?: { type: string; destination: string; prompt: string; user_message?: string };
  meetingIntent?: { type: string; message: string; prompt: string };
  autoShowTravelAssistant?: boolean;
  workspaceActions?: WorkspaceAction[];
}

export interface StoredFileInfo {
  id: string;
  original_name: string;
  mime_type: string;
  size_bytes: number;
  page_count: number;
  total_chars: number;
  preview: string;
  created_at: number;
  storage_key?: string;
  content_url?: string;
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

// ============ 旅游计划 ============
export interface TravelPlan {
  id: string;
  session_id: string;
  title: string;
  departure: string;
  destination: string;
  days: number;
  travel_style: string;
  scenery_preference: string;
  budget: string;
  extra_notes: string;
  markdown_content: string;
  baike_info: {
    summary?: string;
    highlights?: string[];
    best_season?: string;
    error?: string;
    [key: string]: unknown;
  };
  created_at: number;
  updated_at: number;
}

export interface CityInfo {
  name: string;
  province: string;
  pinyin: string;
}

// ============ 通用日程 ============
export type ScheduleCategory = 'travel' | 'meeting' | 'dining' | 'remind' | 'task' | 'other';

export const SCHEDULE_CATEGORY_LABELS: Record<ScheduleCategory, string> = {
  travel: '旅游',
  meeting: '会议',
  dining: '聚餐',
  remind: '提醒',
  task: '任务',
  other: '其他',
};

export const SCHEDULE_CATEGORY_COLORS: Record<ScheduleCategory, string> = {
  travel: '#2b5aed',
  meeting: '#e37318',
  dining: '#00a870',
  remind: '#ed7b84',
  task: '#7c5cff',
  other: '#909399',
};

export interface ScheduleItem {
  id: string;
  session_id: string;
  title: string;
  category: ScheduleCategory;
  start_time: number;
  duration_minutes: number;
  duration_days: number;
  location: string;
  description: string;
  markdown_content: string;
  extra: {
    search_query?: string;
    search_keyword?: string;
    city?: string;
    cost_estimate?: number;
    description?: string;
    place_type?: string;
    place?: MakersMapPlace;
    [key: string]: unknown;
  };
  done: boolean;
  created_at: number;
  updated_at: number;
}

/** Makers 地图和日程只接受地点服务验证后的地点。 */
export interface MakersMapPlace {
  schema_version?: number;
  place_id: string;
  provider?: string;
  name: string;
  address: string;
  latitude: number;
  longitude: number;
  city?: string;
  category?: string;
}

export type WorkspaceActionKind = 'map_recommendation' | 'calendar_changes' | 'meeting_create' | 'image_generate';
export type WorkspaceActionStatus = 'ready' | 'active' | 'awaiting_confirmation' | 'executing' | 'succeeded' | 'failed' | 'cancelled' | 'reconciliation_required';

export interface WorkspaceAction {
  schema_version: number;
  id: string;
  kind: WorkspaceActionKind;
  status: WorkspaceActionStatus;
  version: number;
  payload: {
    title?: string;
    action_text?: string;
    places?: MakersMapPlace[];
    summary?: string;
    changes?: Array<Record<string, unknown>>;
    subject?: string;
    start_time?: string;
    end_time?: string;
    warnings?: string[];
    missing_fields?: string[];
    validation_errors?: string[];
    prompt?: string;
    parent_action_id?: string;
    group_id?: string;
  };
  result?: Record<string, unknown> | null;
  error?: string;
  snapshot_hash?: string;
  idempotency_key?: string;
  attempt?: number;
  lease_owner?: string;
  lease_until?: number;
  provider_request_id?: string;
  reconciliation_required?: boolean;
  created_at?: number;
  updated_at?: number;
}

export interface MakersRoutePlan {
  schema_version: number;
  provider: string;
  mode: 'driving';
  places: MakersMapPlace[];
  path: Array<{ latitude: number; longitude: number }>;
  distance_meters: number;
  duration_seconds: number;
  fare: {
    currency: string;
    basis: string;
    self_driving: { estimate: number; toll: number };
    taxi: { low: number; high: number };
  };
  cache?: { hit: boolean; expires_at: number };
}

// ============ 会议 ============
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

// ============ 主动式 Agent Runtime ============
export interface PendingAction {
  id: string;
  run_id: string;
  skill_name: string;
  snapshot: {
    schema_version?: number;
    input?: Record<string, unknown>;
    confirmation?: Record<string, unknown>;
    [key: string]: unknown;
  };
  snapshot_hash: string;
  version: number;
  idempotency_key: string;
  status: 'draft' | 'awaiting_confirmation' | 'confirmed' | 'executing' | 'succeeded' | 'failed' | 'cancelled' | 'expired';
  expires_at?: number | null;
  result_json?: {
    schema_version?: number;
    content?: string;
    data?: Record<string, unknown>;
    usage?: Record<string, unknown>;
  };
  provider_request_id?: string;
  error?: string;
  reconciliation_required?: boolean;
  created_at: number;
  updated_at: number;
}

export interface AgentObservation {
  id: number;
  run_id: string;
  status: string;
  step: string;
  payload: Record<string, unknown>;
  error: string;
  ts: number;
}

export interface AgentRun {
  id: string;
  event_id?: string | null;
  status: string;
  intent: string;
  plan_json: Record<string, unknown>;
  execution_lane?: string;
  attempt: number;
  max_attempts: number;
  error: string;
  created_at: number;
  updated_at: number;
  finished_at?: number | null;
  observations: AgentObservation[];
  action?: PendingAction;
}

export interface AgentNotification {
  id: string;
  run_id?: string | null;
  event_id?: string | null;
  type: string;
  title: string;
  body: string;
  reason: string;
  source_label: string;
  action_id?: string | null;
  priority: number;
  metadata: Record<string, unknown>;
  created_at: number;
  read_at?: number | null;
  dismissed_at?: number | null;
  snoozed_until?: number | null;
}

export interface NotificationPreferences {
  quiet_hours_start: string;
  quiet_hours_end: string;
  daily_limit: number;
  cooldown_seconds: number;
  enabled: number | boolean;
  updated_at: number;
}

export interface ScheduledJob {
  id: string;
  job_type: string;
  payload: Record<string, unknown>;
  next_run_at: number;
  interval_seconds?: number | null;
  status: string;
  checkpoint: Record<string, unknown>;
  last_error: string;
}

// ============ 记忆、反馈与使用预算 ============
export interface MemoryProposal {
  id: string;
  source_message_id: string;
  candidate_json: {
    schema_version?: number;
    key: string;
    value: unknown;
    confidence?: number;
    reason?: string;
    sensitivity?: string;
    expected_memory_version?: number | null;
  };
  status: 'awaiting_confirmation' | 'confirmed' | 'rejected';
  version: number;
  created_at: number;
  updated_at: number;
}

export interface AgentMemory {
  id: string;
  memory_key: string;
  value_json: unknown;
  confidence: number;
  source_message_id: string;
  sensitivity: string;
  version: number;
  created_at: number;
  updated_at: number;
}

export interface UsageAggregate {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  units: number;
  estimated_cost: number;
}

export interface UsagePreferences {
  daily_budget_cny: number;
  monthly_budget_cny: number;
  enforcement: 'off' | 'soft' | 'hard';
  alert_threshold_percent: number;
  updated_at: number;
}

export interface UsageSummary {
  daily: UsageAggregate;
  monthly: UsageAggregate;
  preferences: UsagePreferences;
  alerts: { daily: boolean; monthly: boolean };
}

export interface FeedbackRecord {
  id: string;
  run_id?: string | null;
  action_id?: string | null;
  feedback_action: 'helpful' | 'unhelpful' | 'dismissed' | 'corrected';
  reason: string;
  metadata: Record<string, unknown>;
  created_at: number;
}

export interface FeedbackResponse {
  feedback: FeedbackRecord;
  adjustment: {
    applied: boolean;
    requires_user_confirmation: boolean;
    suggestions: Array<Record<string, unknown>>;
  };
}

export interface SystemHealth {
  status: 'ok' | 'degraded' | 'unhealthy';
  version: string;
  time: number;
  components: Record<string, {
    status: string;
    [key: string]: unknown;
  }>;
  startup_recovery: Record<string, unknown>;
  restore_applied?: Record<string, unknown> | null;
}

export interface RestoreStageResult {
  staged: boolean;
  restart_required: boolean;
  created_at: number;
  file_count: number;
  database_size_bytes: number;
}
