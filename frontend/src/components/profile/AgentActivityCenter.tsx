import { useCallback, useEffect, useState } from 'react';
import { Button, MessagePlugin, Tag } from 'tdesign-react';
import {
  cancelAgentRun,
  cancelPendingAction,
  confirmPendingAction,
  dismissAgentNotification,
  getNotificationPreferences,
  listAgentNotifications,
  listAgentRuns,
  listPendingActions,
  listScheduledJobs,
  markAgentNotificationRead,
  recordAgentFeedback,
  updateNotificationPreferences,
} from '../../services/api';
import type {
  AgentNotification,
  AgentRun,
  NotificationPreferences,
  PendingAction,
  ScheduledJob,
} from '../../types';

const ACTIVE_ACTIONS = new Set(['awaiting_confirmation', 'confirmed', 'executing']);

function formatTime(ts?: number | null) {
  if (!ts) return '-';
  return new Date(ts * 1000).toLocaleString('zh-CN', { hour12: false });
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    awaiting_confirmation: '待确认',
    confirmed: '已确认',
    queued: '排队中',
    executing: '执行中',
    succeeded: '已完成',
    failed: '失败',
    cancelled: '已取消',
    expired: '已过期',
    skipped: '已跳过',
  };
  return labels[status] || status;
}

/** Action Center + proactive notifications + run timeline. */
export default function AgentActivityCenter() {
  const [actions, setActions] = useState<PendingAction[]>([]);
  const [notifications, setNotifications] = useState<AgentNotification[]>([]);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [jobs, setJobs] = useState<ScheduledJob[]>([]);
  const [preferences, setPreferences] = useState<NotificationPreferences | null>(null);
  const [loadingId, setLoadingId] = useState('');
  const [expanded, setExpanded] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [nextActions, nextNotifications, nextRuns, nextJobs, nextPreferences] = await Promise.all([
        listPendingActions('all'),
        listAgentNotifications(),
        listAgentRuns(),
        listScheduledJobs(),
        getNotificationPreferences(),
      ]);
      setActions(nextActions);
      setNotifications(nextNotifications);
      setRuns(nextRuns);
      setJobs(nextJobs);
      setPreferences(nextPreferences);
    } catch (error) {
      console.warn('Agent Activity Center refresh failed', error);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => { void refresh(); }, 5000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const handleConfirm = async (action: PendingAction) => {
    setLoadingId(action.id);
    try {
      await confirmPendingAction(action.id, action.version);
      MessagePlugin.success('已确认，后台 Executor 正在处理');
      await refresh();
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : '确认失败');
    } finally {
      setLoadingId('');
    }
  };

  const handleRunCancel = async (run: AgentRun) => {
    setLoadingId(run.id);
    try {
      await cancelAgentRun(run.id);
      MessagePlugin.success('任务取消请求已生效');
      await refresh();
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : '取消任务失败');
    } finally {
      setLoadingId('');
    }
  };

  const handleCancel = async (action: PendingAction) => {
    setLoadingId(action.id);
    try {
      await cancelPendingAction(action.id);
      MessagePlugin.success('操作已取消');
      await refresh();
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : '取消失败');
    } finally {
      setLoadingId('');
    }
  };


  const handleNotificationFeedback = async (
    item: AgentNotification,
    action: 'helpful' | 'dismissed',
  ) => {
    setLoadingId(item.id);
    try {
      await recordAgentFeedback({
        run_id: item.run_id,
        action_id: item.action_id,
        action,
        metadata: {
          notification_id: item.id,
          notification_type: item.type,
          source_label: item.source_label,
        },
        client_feedback_id: `notification:${item.id}:${action}`,
      });
      if (action === 'helpful') {
        await markAgentNotificationRead(item.id);
        MessagePlugin.success('感谢反馈');
      } else {
        await dismissAgentNotification(item.id);
        MessagePlugin.success('已忽略，并记录反馈');
      }
      await refresh();
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : '反馈失败');
    } finally {
      setLoadingId('');
    }
  };

  const toggleNotifications = async () => {
    if (!preferences) return;
    try {
      const next = await updateNotificationPreferences({ enabled: !preferences.enabled });
      setPreferences(next);
      MessagePlugin.success(next.enabled ? '主动通知已开启' : '主动通知已关闭');
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : '设置失败');
    }
  };

  const activeActions = actions.filter((item) => ACTIVE_ACTIONS.has(item.status));
  const unread = notifications.filter((item) => !item.read_at).length;
  const activeJobs = jobs.filter((item) => item.status === 'enabled' || item.status === 'running');

  return (
    <div className="my-panel-card" data-testid="agent-activity-center">
      <div className="section-title" style={{ marginBottom: 8 }}>
        <span style={{ marginRight: 6 }}>⚡</span>
        Agent Activity Center
        <Tag size="small" variant="light" style={{ marginLeft: 'auto' }}>
          {activeActions.length} 操作 / {unread} 通知
        </Tag>
      </div>

      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
        <Button size="small" variant="outline" onClick={() => setExpanded((value) => !value)}>
          {expanded ? '收起详情' : '查看详情'}
        </Button>
        <Button size="small" variant="text" onClick={() => { void refresh(); }}>刷新</Button>
        <Button size="small" variant="text" onClick={() => { void toggleNotifications(); }}>
          主动通知：{preferences && preferences.enabled ? '开' : '关'}
        </Button>
      </div>

      {activeActions.length === 0 && notifications.length === 0 ? (
        <div style={{ fontSize: 12, color: 'var(--app-text-3)', padding: '8px 0' }}>
          当前没有待处理操作；日程 Collector 正在后台运行。
        </div>
      ) : null}

      {activeActions.slice(0, expanded ? 20 : 3).map((action) => (
        <div key={action.id} style={{ padding: '8px', border: '1px solid var(--app-border)', borderRadius: 8, marginBottom: 6 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <strong style={{ fontSize: 12 }}>{action.skill_name}</strong>
            <Tag size="small" theme={action.status === 'awaiting_confirmation' ? 'warning' : 'primary'}>
              {statusLabel(action.status)}
            </Tag>
            <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--app-text-3)' }}>
              v{action.version}
            </span>
          </div>
          <div style={{ fontSize: 11, color: 'var(--app-text-2)', marginTop: 4, wordBreak: 'break-word' }}>
            {JSON.stringify(action.snapshot.input || {})}
          </div>
          {action.error ? <div style={{ color: 'var(--td-error-color)', fontSize: 11 }}>{action.error}</div> : null}
          {action.status === 'awaiting_confirmation' ? (
            <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
              <Button size="small" theme="primary" loading={loadingId === action.id} onClick={() => { void handleConfirm(action); }}>
                确认执行
              </Button>
              <Button size="small" variant="outline" onClick={() => { void handleCancel(action); }}>取消</Button>
            </div>
          ) : null}
        </div>
      ))}

      {notifications.slice(0, expanded ? 20 : 3).map((item) => (
        <div key={item.id} style={{ padding: '8px', background: 'var(--app-bg)', borderRadius: 8, marginBottom: 6, opacity: item.read_at ? 0.68 : 1 }}>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <strong style={{ fontSize: 12 }}>{item.title}</strong>
            {!item.read_at ? <span style={{ color: '#2b5aed' }}>●</span> : null}
            <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--app-text-3)' }}>{formatTime(item.created_at)}</span>
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--app-text-2)', marginTop: 3 }}>{item.body}</div>
          <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
            {!item.read_at ? (
              <Button size="small" variant="text" onClick={() => { void markAgentNotificationRead(item.id).then(refresh); }}>已读</Button>
            ) : null}
            <Button
              size="small"
              variant="text"
              loading={loadingId === item.id}
              onClick={() => { void handleNotificationFeedback(item, 'helpful'); }}
            >
              有帮助
            </Button>
            <Button
              size="small"
              variant="text"
              loading={loadingId === item.id}
              onClick={() => { void handleNotificationFeedback(item, 'dismissed'); }}
            >
              忽略
            </Button>
          </div>
        </div>
      ))}

      {expanded ? (
        <details style={{ marginTop: 8 }} open>
          <summary style={{ fontSize: 12, cursor: 'pointer' }}>Run 时间线（最近 {Math.min(runs.length, 10)} 条）</summary>
          {runs.slice(0, 10).map((run) => (
            <details key={run.id} style={{ padding: '5px 0', borderBottom: '1px solid var(--app-border)' }}>
              <summary style={{ fontSize: 11.5, cursor: 'pointer' }}>
                {run.intent || '未分类'} · {statusLabel(run.status)} · {run.id.slice(-8)}
              </summary>
              <div style={{ paddingLeft: 10, marginTop: 4 }}>
                {['queued', 'executing'].includes(run.status) && run.action?.status !== 'executing' ? (
                  <Button
                    size="small"
                    variant="outline"
                    loading={loadingId === run.id}
                    onClick={() => { void handleRunCancel(run); }}
                    style={{ marginBottom: 4 }}
                  >
                    取消任务
                  </Button>
                ) : null}
                {run.observations.map((observation) => (
                  <div key={observation.id} style={{ fontSize: 10.5, color: observation.error ? 'var(--td-error-color)' : 'var(--app-text-2)' }}>
                    {formatTime(observation.ts)} · {observation.status} · {observation.step}
                  </div>
                ))}
              </div>
            </details>
          ))}
          <div style={{ marginTop: 8, fontSize: 11, color: 'var(--app-text-3)' }}>
            后台任务：{activeJobs.map((job) => `${job.job_type}(${job.status})`).join('、') || '无'}
          </div>
          {preferences ? (
            <div style={{ marginTop: 5, fontSize: 11, color: 'var(--app-text-3)' }}>
              静默时段 {preferences.quiet_hours_start}–{preferences.quiet_hours_end}，每日上限 {preferences.daily_limit} 条，冷却 {preferences.cooldown_seconds}s
            </div>
          ) : null}
        </details>
      ) : null}
    </div>
  );
}
