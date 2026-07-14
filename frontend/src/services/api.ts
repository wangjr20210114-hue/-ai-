import type { ChatMessage, ScheduleItem, StoredFileInfo } from '../types';
import { authorizedFetch, withEdgeOneAuth } from './auth';
import { makersConversationHeaders } from './conversation';

let tencentMapBrowserKeyPromise: Promise<string> | null = null;

async function makersTravelRequest<T>(userId: string, body: Record<string, unknown>): Promise<T> {
  const response = await authorizedFetch('/travel', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...makersConversationHeaders(userId),
    },
    body: JSON.stringify({ user_id: userId, ...body }),
  });
  const data = await response.json().catch(() => ({})) as T & { error?: string };
  if (!response.ok) throw new Error(data.error || `旅行服务请求失败（${response.status}）`);
  return data;
}

export function getTencentMapBrowserKey(): Promise<string> {
  if (!tencentMapBrowserKeyPromise) {
    tencentMapBrowserKeyPromise = makersTravelRequest<{ key?: string }>(
      'map-config',
      { action: 'public_map_config' },
    ).then((data) => String(data.key || '').trim()).catch(() => '');
  }
  return tencentMapBrowserKeyPromise;
}

export interface MakersTravelCheckpoint {
  id?: string;
  city?: string;
  start_date?: string;
  days?: number;
  tentative_date?: boolean;
  schedules: ScheduleItem[];
}

export interface BootstrapData {
  messages: ChatMessage[];
  schedules?: ScheduleItem[];
  travel_plan?: MakersTravelCheckpoint;
}

export async function bootstrapApp(conversationId: string): Promise<BootstrapData> {
  try {
    const response = await authorizedFetch('/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...makersConversationHeaders(conversationId),
      },
      body: JSON.stringify({ conversation_id: conversationId }),
    });
    if (response.ok) return response.json();
  } catch {
    // A new conversation has no checkpoint yet.
  }
  return { messages: [] };
}

export async function uploadDocument(conversationId: string, file: File): Promise<StoredFileInfo> {
  const signed = await authorizedFetch('/files', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      conversation_id: conversationId,
      name: file.name,
      content_type: file.type || 'application/pdf',
      size: file.size,
    }),
  });
  const upload = await signed.json().catch(() => ({})) as {
    url?: string;
    key?: string;
    content_url?: string;
    error?: string;
  };
  if (!signed.ok || !upload.url || !upload.key) {
    throw new Error(upload.error || '无法创建 Makers Blob 上传地址');
  }
  const stored = await fetch(upload.url, {
    method: 'PUT',
    headers: { 'Content-Type': file.type || 'application/pdf' },
    body: file,
  });
  if (!stored.ok) throw new Error('上传到 Makers Blob 失败');
  return {
    id: upload.key,
    original_name: file.name,
    mime_type: file.type || 'application/pdf',
    size_bytes: file.size,
    page_count: 0,
    total_chars: 0,
    preview: '文件已保存到 EdgeOne Makers Blob。',
    created_at: Date.now(),
    storage_key: upload.key,
    content_url: upload.content_url ? withEdgeOneAuth(upload.content_url) : undefined,
  };
}

export async function listSchedules(userId: string): Promise<ScheduleItem[]> {
  const data = await makersTravelRequest<{ schedules: ScheduleItem[] }>(userId, { action: 'snapshot' });
  return data.schedules || [];
}

export async function updateSchedule(
  userId: string,
  scheduleId: string,
  schedule: Partial<ScheduleItem>,
): Promise<{ ok: boolean }> {
  return makersTravelRequest(userId, {
    action: 'upsert_schedule',
    schedule: { ...schedule, id: scheduleId },
  });
}

export async function deleteSchedule(userId: string, scheduleId: string): Promise<{ ok: boolean }> {
  return makersTravelRequest(userId, { action: 'delete_schedule', schedule_id: scheduleId });
}

export async function toggleScheduleDone(
  userId: string,
  scheduleId: string,
  done: boolean,
): Promise<{ ok: boolean }> {
  return makersTravelRequest(userId, { action: 'toggle_schedule', schedule_id: scheduleId, done });
}

export interface DailyRouteLocation {
  id: string;
  keyword: string;
  name: string;
  address: string;
  lat: number;
  lng: number;
  alternatives: {
    id: string;
    title: string;
    address: string;
    tel: string;
    lat: number;
    lng: number;
  }[];
  ticket?: number;
  cost_estimate?: number;
  stay_time?: number;
  place_type?: string;
}

export interface WeatherData {
  error?: string;
  temperature?: number;
  weather?: string;
  tips?: string;
}

export interface DailyRouteData {
  city: string;
  locations: DailyRouteLocation[];
  segments: { from: string; to: string; distance: number; duration: number; toll: number }[];
  polyline: number[];
  total_distance: number;
  total_duration: number;
  total_distance_km: number;
  total_duration_hours: number;
  total_toll: number;
  cost_estimate: { self_driving: number; taxi: number; toll: number; poi_cost?: number; total?: number };
  weather: WeatherData;
  api_calls?: number;
  error?: string;
}

export async function planDailyRoute(params: {
  city: string;
  locations: {
    id?: string;
    keyword: string;
    lat?: number;
    lng?: number;
    name?: string;
    address?: string;
    alternatives?: DailyRouteLocation['alternatives'];
  }[];
}): Promise<DailyRouteData> {
  return makersTravelRequest<DailyRouteData>('daily-route', { action: 'daily_route', ...params });
}
