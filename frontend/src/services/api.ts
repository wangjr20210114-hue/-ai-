import type { TravelPlan, CityInfo, ScheduleItem, MeetingResult } from '../types';

const BASE = '/api';

// ============ 旅游计划 ============

export async function analyzeTravelIntent(params: {
  session_id: string;
  message: string;
  collected?: Record<string, any>;
  history?: string[];
}): Promise<{
  collected?: Record<string, any>;
  missing?: string[];
  next_question?: {
    field: string;
    question: string;
    options: string[];
    multi: boolean;
    allow_custom: boolean;
    is_date?: boolean;
  };
  ready?: boolean;
  reasoning?: string;
  error?: string;
}> {
  const res = await fetch(`${BASE}/travel/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error('分析失败');
  return res.json();
}

export async function searchCities(keyword: string): Promise<CityInfo[]> {
  const res = await fetch(`${BASE}/cities?keyword=${encodeURIComponent(keyword)}`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.cities || [];
}

export async function generateTravelPlan(params: {
  session_id: string;
  departure: string;
  destination: string;
  days?: number;
  start_date?: string;
  end_date?: string;
  travel_style: string;
  scenery_preference: string;
  budget: string;
  extra_notes: string;
}): Promise<{ plan?: TravelPlan; cost?: any; error?: string; start_date?: string; end_date?: string; start_ts?: number; parsed_schedules?: any[] }> {
  const res = await fetch(`${BASE}/travel/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error('生成旅游计划失败');
  return res.json();
}

export async function saveTravelPlan(sessionId: string, plan: TravelPlan): Promise<{ ok: boolean; plan_id: string }> {
  const res = await fetch(`${BASE}/travel/plans`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, plan }),
  });
  if (!res.ok) throw new Error('保存计划失败');
  return res.json();
}

export async function updateTravelPlan(sessionId: string, planId: string, plan: TravelPlan): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE}/travel/plans/${sessionId}/${planId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, plan }),
  });
  if (!res.ok) throw new Error('更新计划失败');
  return res.json();
}

export async function deleteTravelPlan(sessionId: string, planId: string): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE}/travel/plans/${sessionId}/${planId}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('删除计划失败');
  return res.json();
}

export async function listTravelPlans(sessionId: string): Promise<TravelPlan[]> {
  const res = await fetch(`${BASE}/travel/plans/${sessionId}`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.plans || [];
}

// ============ 通用日程 ============

export async function listSchedules(sessionId: string): Promise<ScheduleItem[]> {
  const res = await fetch(`${BASE}/schedules/${sessionId}`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.schedules || [];
}

export async function saveSchedule(sessionId: string, schedule: Partial<ScheduleItem>): Promise<{ ok: boolean; schedule_id: string; conflicts?: any[] }> {
  const res = await fetch(`${BASE}/schedules`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, schedule }),
  });
  if (!res.ok) throw new Error('保存日程失败');
  return res.json();
}

export async function updateSchedule(sessionId: string, scheduleId: string, schedule: Partial<ScheduleItem>): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE}/schedules/${sessionId}/${scheduleId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, schedule }),
  });
  if (!res.ok) throw new Error('更新日程失败');
  return res.json();
}

export async function deleteSchedule(sessionId: string, scheduleId: string): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE}/schedules/${sessionId}/${scheduleId}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('删除日程失败');
  return res.json();
}

export async function toggleScheduleDone(sessionId: string, scheduleId: string, done: boolean): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE}/schedules/${sessionId}/${scheduleId}/done?done=${done}`, {
    method: 'PATCH',
  });
  if (!res.ok) throw new Error('操作失败');
  return res.json();
}

// ============ 腾讯地图 ============

export interface PlacePlan {
  id: string;
  title: string;
  address: string;
  tel: string;
  category: string;
  lat: number;
  lng: number;
  distance: number;
}

export async function searchPlaces(city: string, keyword: string): Promise<{ plans: PlacePlan[]; city: string; keyword: string }> {
  const res = await fetch(`${BASE}/map/search?city=${encodeURIComponent(city)}&keyword=${encodeURIComponent(keyword)}`);
  if (!res.ok) return { plans: [], city, keyword };
  return res.json();
}

// ============ 每日路线 ============

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

export interface DailyRouteData {
  city: string;
  locations: DailyRouteLocation[];
  segments: { from: string; to: string; distance: number; duration: number; toll: number }[];
  polyline: number[][];
  total_distance: number;
  total_duration: number;
  total_distance_km: number;
  total_duration_hours: number;
  total_toll: number;
  cost_estimate: { self_driving: number; taxi: number; toll: number; poi_cost?: number; total?: number };
  weather: any;
  api_calls?: number;
  error?: string;
}

export async function planDailyRoute(params: {
  city: string;
  locations: { keyword: string; lat?: number; lng?: number; name?: string; address?: string; alternatives?: any[] }[];
}): Promise<DailyRouteData> {
  const res = await fetch(`${BASE}/map/daily-route`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error('路线规划失败');
  return res.json();
}

export async function planRoute(origin: string, destination: string, waypoints?: string[]): Promise<{
  origin?: string;
  origin_location?: { lat: number; lng: number };
  destination?: string;
  destination_location?: { lat: number; lng: number };
  waypoints?: string[];
  waypoint_locations?: { lat: number; lng: number }[];
  segments?: { from: string; to: string; distance: number; duration: number }[];
  total_distance?: number;
  total_duration?: number;
  total_distance_km?: number;
  total_duration_hours?: number;
  polyline?: number[][];
  cost_estimate?: { self_driving: number; taxi: number; high_speed_rail: number };
  error?: string;
}> {
  const res = await fetch(`${BASE}/map/route`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ origin, destination, waypoints }),
  });
  if (!res.ok) throw new Error('路线规划失败');
  return res.json();
}

// ============ 会议 ============

export async function createMeeting(sessionId: string, message: string): Promise<MeetingResult> {
  const res = await fetch(`${BASE}/meeting/create`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message }),
  });
  if (!res.ok) throw new Error('创建会议失败');
  return res.json();
}

export async function checkMeetingStatus(): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch(`${BASE}/meeting/status`);
  if (!res.ok) return { ok: false, error: '检查失败' };
  return res.json();
}

// ============ AI 生图 ============

export async function generateImage(prompt: string): Promise<{ ok: boolean; image_url?: string; error?: string }> {
  const res = await fetch(`${BASE}/image/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
  });
  return res.json();
}
