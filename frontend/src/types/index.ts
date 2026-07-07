// 全局类型定义

export type ThemeMode = 'light' | 'dark';

// ============ 技能结果（通用） ============
export interface SkillInfo {
  intent: string;       // "travel", "meeting", "news", "image", "translation", "paper", "chat"
  mode: string;         // "auto" | "suggest" | "immediate"
  content: string;      // Markdown 文本
  icon: string;          // emoji
  action_label: string;  // 按钮文案
  params: Record<string, any>;
  data: Record<string, any>;
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
  parsedSchedules?: any[];

  // 论文数据
  papers?: PaperInfo[];
  paperFileId?: string;
  paperFileName?: string;
  paperTitle?: string;
  showPaperReader?: boolean;

  // 兼容旧字段
  travelIntent?: { type: string; destination: string; prompt: string; user_message?: string };
  meetingIntent?: { type: string; message: string; prompt: string };
  autoShowTravelAssistant?: boolean;
}

export interface WSMessage {
  type:
    | 'user_activity'
    | 'suggestion'
    | 'chat_reply'
    | 'chat_thinking'
    | 'error'
    | 'ack'
    | 'ping'
    | 'pong';
  payload: Record<string, any>;
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
  baike_info: Record<string, any>;
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
  extra: Record<string, any>;
  done: boolean;
  created_at: number;
  updated_at: number;
}

// ============ 会议 ============
export interface MeetingResult {
  ok: boolean;
  meeting_id?: string;
  meeting_code?: string;
  join_url?: string;
  subject?: string;
  start_time?: string;
  error?: string;
}
