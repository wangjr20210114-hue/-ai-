import type { ChatMessage, TravelPlan, CityInfo, ScheduleItem, MeetingResult, StoredFileInfo, TravelCollected } from '../types';

import { authorizedFetch } from './auth';
const BASE = '/api';

export async function bootstrapApp(conversationId: string): Promise<{ messages: ChatMessage[] }> {
  const res = await authorizedFetch(`${BASE}/bootstrap?conversation_id=${encodeURIComponent(conversationId)}`);
  if (!res.ok) throw new Error('初始化会话失败');
  return res.json();
}

export async function saveConversationMessage(conversationId: string, message: ChatMessage): Promise<void> {
  const res = await authorizedFetch(`${BASE}/conversations/${encodeURIComponent(conversationId)}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: message.id, role: message.role, content: message.content, ts: message.ts, metadata: message }),
  });
  if (!res.ok) throw new Error('保存消息失败');
}

export async function uploadDocument(conversationId: string, file: File): Promise<StoredFileInfo> {
  const body = new FormData();
  body.append('conversation_id', conversationId);
  body.append('file', file, file.name);
  const res = await authorizedFetch(`${BASE}/files`, { method: 'POST', body });
  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error(error.detail || '上传失败');
  }
  const data = await res.json();
  return data.file;
}

// ============ 旅游计划 ============

export async function analyzeTravelIntent(params: {
  session_id: string;
  message: string;
  collected?: TravelCollected;
  history?: string[];
}): Promise<{
  collected?: TravelCollected;
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
  context?: Record<string, unknown>;
  error?: string;
}> {
  const res = await authorizedFetch(`${BASE}/travel/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error('分析失败');
  return res.json();
}

export async function searchCities(keyword: string): Promise<CityInfo[]> {
  const res = await authorizedFetch(`${BASE}/cities?keyword=${encodeURIComponent(keyword)}`);
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
}): Promise<{ plan?: TravelPlan; cost?: CostRecord; error?: string; start_date?: string; end_date?: string; start_ts?: number; parsed_schedules?: Partial<ScheduleItem>[] }> {
  const res = await authorizedFetch(`${BASE}/travel/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error('生成旅游计划失败');
  return res.json();
}

export async function saveTravelPlan(sessionId: string, plan: TravelPlan): Promise<{ ok: boolean; plan_id: string }> {
  const res = await authorizedFetch(`${BASE}/travel/plans`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, plan }),
  });
  if (!res.ok) throw new Error('保存计划失败');
  return res.json();
}

export async function updateTravelPlan(sessionId: string, planId: string, plan: TravelPlan): Promise<{ ok: boolean }> {
  const res = await authorizedFetch(`${BASE}/travel/plans/${sessionId}/${planId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, plan }),
  });
  if (!res.ok) throw new Error('更新计划失败');
  return res.json();
}

export async function deleteTravelPlan(sessionId: string, planId: string): Promise<{ ok: boolean }> {
  const res = await authorizedFetch(`${BASE}/travel/plans/${sessionId}/${planId}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('删除计划失败');
  return res.json();
}

export async function listTravelPlans(sessionId: string): Promise<TravelPlan[]> {
  const res = await authorizedFetch(`${BASE}/travel/plans/${sessionId}`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.plans || [];
}

// ============ 通用日程 ============

export async function listSchedules(sessionId: string): Promise<ScheduleItem[]> {
  const res = await authorizedFetch(`${BASE}/schedules/${sessionId}`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.schedules || [];
}

export async function saveSchedule(sessionId: string, schedule: Partial<ScheduleItem>): Promise<{ ok: boolean; schedule_id: string; conflicts?: ScheduleItem[] }> {
  const res = await authorizedFetch(`${BASE}/schedules`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, schedule }),
  });
  if (!res.ok) throw new Error('保存日程失败');
  return res.json();
}

export async function updateSchedule(sessionId: string, scheduleId: string, schedule: Partial<ScheduleItem>): Promise<{ ok: boolean }> {
  const res = await authorizedFetch(`${BASE}/schedules/${sessionId}/${scheduleId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, schedule }),
  });
  if (!res.ok) throw new Error('更新日程失败');
  return res.json();
}

export async function deleteSchedule(sessionId: string, scheduleId: string): Promise<{ ok: boolean }> {
  const res = await authorizedFetch(`${BASE}/schedules/${sessionId}/${scheduleId}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('删除日程失败');
  return res.json();
}

export async function toggleScheduleDone(sessionId: string, scheduleId: string, done: boolean): Promise<{ ok: boolean }> {
  const res = await authorizedFetch(`${BASE}/schedules/${sessionId}/${scheduleId}/done?done=${done}`, {
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
  const res = await authorizedFetch(`${BASE}/map/search?city=${encodeURIComponent(city)}&keyword=${encodeURIComponent(keyword)}`);
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
  locations: { keyword: string; lat?: number; lng?: number; name?: string; address?: string; alternatives?: DailyRouteLocation['alternatives'] }[];
}): Promise<DailyRouteData> {
  const res = await authorizedFetch(`${BASE}/map/daily-route`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error('路线规划失败');
  return res.json();
}

export interface RoutePlanData {
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
  polyline?: number[];
  cost_estimate?: { self_driving: number; taxi: number; toll: number };
  weather?: WeatherData;
  error?: string;
}

export async function planRoute(origin: string, destination: string, waypoints?: string[]): Promise<RoutePlanData> {
  const res = await authorizedFetch(`${BASE}/map/route`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ origin, destination, waypoints }),
  });
  if (!res.ok) throw new Error('路线规划失败');
  return res.json();
}

export interface CostRecord {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_yuan: number;
}

export interface WeatherData {
  error?: string;
  temperature?: number;
  weather?: string;
  tips?: string;
}

// ============ 会议 ============

export async function createMeeting(sessionId: string, message: string): Promise<MeetingResult> {
  const res = await authorizedFetch(`${BASE}/meeting/create`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message }),
  });
  if (!res.ok) throw new Error('创建会议失败');
  return res.json();
}

export async function checkMeetingStatus(): Promise<{ ok: boolean; error?: string }> {
  const res = await authorizedFetch(`${BASE}/meeting/status`);
  if (!res.ok) return { ok: false, error: '检查失败' };
  return res.json();
}

// ============ AI 生图 ============

export async function generateImage(prompt: string): Promise<{ ok: boolean; image_url?: string; prompt?: string; error?: string }> {
  const res = await authorizedFetch(`${BASE}/image/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
  });
  return res.json();
}

// ============ 主动式 Agent Runtime ============

export async function listAgentRuns(status?: string): Promise<import('../types').AgentRun[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : '';
  const res = await authorizedFetch(`${BASE}/runs${query}`);
  if (!res.ok) throw new Error('读取 Agent 运行记录失败');
  return (await res.json()).runs || [];
}

export async function getAgentRun(runId: string): Promise<import('../types').AgentRun> {
  const res = await authorizedFetch(`${BASE}/runs/${encodeURIComponent(runId)}`);
  if (!res.ok) throw new Error('读取 Agent 运行记录失败');
  return (await res.json()).run;
}

export async function cancelAgentRun(runId: string): Promise<import('../types').AgentRun> {
  const res = await authorizedFetch(`${BASE}/runs/${encodeURIComponent(runId)}/cancel`, { method: 'POST' });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : '取消 Agent 任务失败');
  }
  return (await res.json()).run;
}

export async function listPendingActions(status = 'all'): Promise<import('../types').PendingAction[]> {
  const res = await authorizedFetch(`${BASE}/actions?status=${encodeURIComponent(status)}`);
  if (!res.ok) throw new Error('读取待确认操作失败');
  return (await res.json()).actions || [];
}

export async function getPendingAction(actionId: string): Promise<import('../types').PendingAction> {
  const res = await authorizedFetch(`${BASE}/actions/${encodeURIComponent(actionId)}`);
  if (!res.ok) throw new Error('读取操作状态失败');
  return (await res.json()).action;
}

export async function confirmPendingAction(actionId: string, version: number): Promise<import('../types').PendingAction> {
  const res = await authorizedFetch(`${BASE}/actions/${encodeURIComponent(actionId)}/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ version }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : '确认操作失败');
  }
  return (await res.json()).action;
}

export async function cancelPendingAction(actionId: string): Promise<import('../types').PendingAction> {
  const res = await authorizedFetch(`${BASE}/actions/${encodeURIComponent(actionId)}/cancel`, { method: 'POST' });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : '取消操作失败');
  }
  return (await res.json()).action;
}

export async function waitForPendingAction(
  actionId: string,
  timeoutMs = 120_000,
  pollMs = 800,
): Promise<import('../types').PendingAction> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const action = await getPendingAction(actionId);
    if (['succeeded', 'failed', 'cancelled', 'expired'].includes(action.status)) return action;
    await new Promise((resolve) => window.setTimeout(resolve, pollMs));
  }
  throw new Error('操作仍在后台执行，可在 Action Center 中继续查看');
}

export async function listAgentNotifications(since?: number): Promise<import('../types').AgentNotification[]> {
  const query = since ? `?since=${encodeURIComponent(since)}` : '';
  const res = await authorizedFetch(`${BASE}/notifications${query}`);
  if (!res.ok) throw new Error('读取通知失败');
  return (await res.json()).notifications || [];
}

export async function markAgentNotificationRead(notificationId: string): Promise<void> {
  const res = await authorizedFetch(`${BASE}/notifications/${encodeURIComponent(notificationId)}/read`, { method: 'POST' });
  if (!res.ok) throw new Error('标记通知失败');
}

export async function dismissAgentNotification(notificationId: string): Promise<void> {
  const res = await authorizedFetch(`${BASE}/notifications/${encodeURIComponent(notificationId)}/dismiss`, { method: 'POST' });
  if (!res.ok) throw new Error('忽略通知失败');
}

export async function getNotificationPreferences(): Promise<import('../types').NotificationPreferences> {
  const res = await authorizedFetch(`${BASE}/notification-preferences`);
  if (!res.ok) throw new Error('读取通知设置失败');
  return (await res.json()).preferences;
}

export async function updateNotificationPreferences(
  changes: Partial<import('../types').NotificationPreferences>,
): Promise<import('../types').NotificationPreferences> {
  const res = await authorizedFetch(`${BASE}/notification-preferences`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(changes),
  });
  if (!res.ok) throw new Error('更新通知设置失败');
  return (await res.json()).preferences;
}

export async function listScheduledJobs(): Promise<import('../types').ScheduledJob[]> {
  const res = await authorizedFetch(`${BASE}/scheduled-jobs`);
  if (!res.ok) throw new Error('读取定时任务失败');
  return (await res.json()).jobs || [];
}

// ============ 记忆、反馈与使用预算 ============
export async function listMemoryProposals(status = 'awaiting_confirmation'): Promise<import('../types').MemoryProposal[]> {
  const res = await authorizedFetch(`${BASE}/memory-proposals?status=${encodeURIComponent(status)}`);
  if (!res.ok) throw new Error('读取记忆提案失败');
  return (await res.json()).proposals || [];
}

export async function confirmMemoryProposal(
  proposalId: string,
  version: number,
): Promise<{ proposal: import('../types').MemoryProposal; memory: import('../types').AgentMemory }> {
  const res = await authorizedFetch(`${BASE}/memory-proposals/${encodeURIComponent(proposalId)}/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ version }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : '确认记忆失败');
  }
  return await res.json();
}

export async function rejectMemoryProposal(proposalId: string): Promise<void> {
  const res = await authorizedFetch(`${BASE}/memory-proposals/${encodeURIComponent(proposalId)}/reject`, { method: 'POST' });
  if (!res.ok) throw new Error('拒绝记忆提案失败');
}

export async function listAgentMemories(): Promise<import('../types').AgentMemory[]> {
  const res = await authorizedFetch(`${BASE}/memories`);
  if (!res.ok) throw new Error('读取长期记忆失败');
  return (await res.json()).memories || [];
}

export async function deleteAgentMemory(memoryId: string): Promise<void> {
  const res = await authorizedFetch(`${BASE}/memories/${encodeURIComponent(memoryId)}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('删除记忆失败');
}

export async function exportAgentMemories(): Promise<{ schema_version: number; memories: import('../types').AgentMemory[] }> {
  const res = await authorizedFetch(`${BASE}/memories-export`);
  if (!res.ok) throw new Error('导出记忆失败');
  return await res.json();
}

export async function recordAgentFeedback(input: {
  run_id?: string | null;
  action_id?: string | null;
  action: 'helpful' | 'unhelpful' | 'dismissed' | 'corrected';
  reason?: string;
  metadata?: Record<string, unknown>;
  client_feedback_id?: string;
}): Promise<import('../types').FeedbackResponse> {
  const res = await authorizedFetch(`${BASE}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error('记录反馈失败');
  return await res.json();
}

export async function getUsageSummary(): Promise<import('../types').UsageSummary> {
  const res = await authorizedFetch(`${BASE}/usage-summary`);
  if (!res.ok) throw new Error('读取使用量失败');
  return await res.json();
}

export async function updateUsagePreferences(
  changes: Partial<import('../types').UsagePreferences>,
): Promise<import('../types').UsagePreferences> {
  const res = await authorizedFetch(`${BASE}/usage-preferences`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(changes),
  });
  if (!res.ok) throw new Error('更新预算设置失败');
  return (await res.json()).preferences;
}

// ============ 系统健康与备份恢复 ============
export async function getSystemHealth(): Promise<import('../types').SystemHealth> {
  const res = await authorizedFetch(`${BASE}/system/health`);
  if (!res.ok) throw new Error('读取系统健康状态失败');
  return await res.json();
}

export async function downloadSystemBackup(): Promise<string> {
  const res = await authorizedFetch(`${BASE}/system/backup/export`, { method: 'POST' });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : '生成备份失败');
  }
  const disposition = res.headers.get('Content-Disposition') || '';
  const matched = disposition.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i);
  const filename = matched ? decodeURIComponent(matched[1].replace(/"/g, '')) : 'yuanbao-agent-backup.zip';
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
  } finally {
    URL.revokeObjectURL(url);
  }
  return filename;
}

export async function stageSystemRestore(file: File): Promise<import('../types').RestoreStageResult> {
  const body = new FormData();
  body.append('file', file, file.name);
  const res = await authorizedFetch(`${BASE}/system/backup/restore?confirm=true`, {
    method: 'POST',
    body,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : '备份校验失败');
  }
  return await res.json();
}
