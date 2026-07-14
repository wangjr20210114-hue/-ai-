export type ThemeMode = 'light' | 'dark';

export interface SkillInfo {
  intent: string;
  mode: string;
  content: string;
  icon: string;
  action_label: string;
  params: Record<string, unknown>;
  data: Record<string, unknown>;
}

export interface SearchResultItem {
  id: string;
  source: string;
  title: string;
  snippet: string;
  url: string;
  account_name?: string;
  gh_id?: string;
  avatar?: string;
  image?: string;
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
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'ai';
  content: string;
  ts: number;
  streaming?: boolean;
  followUps?: string[];
  mapPlaces?: MakersMapPlace[];
  skill?: SkillInfo;
  searchResults?: SearchMeta;
}

export interface MakersMapPlace {
  id?: string;
  name: string;
  address: string;
  lat: number;
  lng: number;
  source?: string;
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
    lat?: number;
    lng?: number;
    [key: string]: unknown;
  };
  done: boolean;
  created_at: number;
  updated_at: number;
}
