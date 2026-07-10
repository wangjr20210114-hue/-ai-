// 全局类型定义

export type ThemeMode = 'light' | 'dark';

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
  source: string;           // "web" | "wechat" | "zhihu" | "baike" | "wsa"
  title: string;
  snippet: string;
  url: string;
  account_name?: string;    // 微信公众号名
  gh_id?: string;           // 公众号原始ID
  avatar?: string;          // 公众号头像URL
  image?: string;           // 百科图片等
}

export interface SearchMeta {
  query: string;
  results: SearchResultItem[];
  images: string[];
  sources_used: string[];
  total: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'ai';
  content: string;
  ts: number;
  streaming?: boolean;      // 是否正在流式输出
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
    [key: string]: unknown;
  };
  done: boolean;
  created_at: number;
  updated_at: number;
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
