import { useEffect, useMemo, useState } from 'react';
import { Button, MessagePlugin } from 'tdesign-react';
import { NotificationIcon } from 'tdesign-icons-react';
import { useAppDispatch, useAppState } from '../../store/appState';
import { proactiveOperation } from '../../services/api';

function clock(timestamp?: number | null): string {
  if (!timestamp) return '';
  return new Date(timestamp * 1000).toLocaleString('zh-CN', {
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
  });
}

const NOTIFIED_KEY = 'yuanbao:proactive:notified';

function deliverBrowserNotifications(items: Array<{ id: string; title: string; body: string; status: string }>) {
  if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return;
  let delivered: string[] = [];
  try { delivered = JSON.parse(localStorage.getItem(NOTIFIED_KEY) || '[]') as string[]; } catch { delivered = []; }
  const seen = new Set(delivered);
  for (const item of items) {
    if (item.status !== 'unread' || seen.has(item.id)) continue;
    new Notification(item.title, { body: item.body, tag: item.id });
    seen.add(item.id);
  }
  localStorage.setItem(NOTIFIED_KEY, JSON.stringify(Array.from(seen).slice(-200)));
}

export default function ProactiveBriefPanel() {
  const { proactive, conversationId } = useAppState();
  const dispatch = useAppDispatch();
  const [mutating, setMutating] = useState('');
  const [showSettings, setShowSettings] = useState(false);
  const [showRuns, setShowRuns] = useState(false);
  const notifications = useMemo(
    () => (proactive?.notifications || []).filter((item) => item.status !== 'dismissed').slice(0, 8),
    [proactive],
  );
  const unread = notifications.filter((item) => item.status === 'unread').length;
  const pendingWorkflows = (proactive?.workflows || []).filter((item) => item.status === 'awaiting_confirmation');
  const activeWorkflows = (proactive?.workflows || []).filter((item) => item.status === 'active');

  useEffect(() => {
    let disposed = false;
    const refresh = () => {
      void proactiveOperation(conversationId).then((next) => {
        if (!disposed) {
          dispatch({ type: 'HYDRATE_PROACTIVE', payload: next });
          deliverBrowserNotifications(next.notifications || []);
        }
      }).catch((error) => console.warn('proactive inbox refresh failed', error));
    };
    const timer = window.setInterval(refresh, 60_000);
    window.addEventListener('yuanbao:calendar-changed', refresh);
    return () => {
      disposed = true;
      window.clearInterval(timer);
      window.removeEventListener('yuanbao:calendar-changed', refresh);
    };
  }, [conversationId, dispatch]);

  const run = async (key: string, operation: string, input: Record<string, unknown> = {}) => {
    setMutating(key);
    try {
      const next = await proactiveOperation(conversationId, operation, input);
      dispatch({ type: 'HYDRATE_PROACTIVE', payload: next });
      return next;
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : '主动服务操作失败');
      return null;
    } finally { setMutating(''); }
  };

  const setPreferences = async (changes: Record<string, unknown>) => {
    const preferences = { ...(proactive?.preferences || {}), ...changes };
    await run('preferences', 'update_preferences', { preferences });
  };

  const fillDraft = async (id: string, prompt: string) => {
    dispatch({ type: 'SET_DRAFT', payload: prompt });
    const item = notifications.find((notification) => notification.id === id);
    if (item?.status === 'unread') await run(`read:${id}`, 'mark_read', { notification_id: id });
  };

  return (
    <div className="my-panel-card proactive-brief-card">
      <div className="section-title proactive-title">
        <span><NotificationIcon size="16px" /> 主动提醒</span>
        {unread > 0 && <span className="proactive-count">{unread}</span>}
      </div>

      <div className="proactive-toolbar">
        <button
          type="button"
          className={`proactive-power ${proactive?.preferences.enabled !== false ? 'is-on' : ''}`}
          onClick={() => { void setPreferences({ enabled: proactive?.preferences.enabled === false }); }}
          disabled={mutating === 'preferences'}
        >
          {proactive?.preferences.enabled !== false ? '主动服务已开启' : '主动服务已暂停'}
        </button>
        <button type="button" onClick={() => setShowSettings((value) => !value)}>设置</button>
        <button type="button" onClick={() => setShowRuns((value) => !value)}>运行记录</button>
      </div>

      {showSettings && proactive?.preferences && (
        <div className="proactive-settings">
          <label>
            主动权限
            <select
              value={proactive.preferences.autonomy_mode || 'propose'}
              onChange={(event) => { void setPreferences({ autonomy_mode: event.target.value }); }}
            >
              <option value="observe">仅观察</option>
              <option value="remind">可提醒</option>
              <option value="propose">可提案</option>
              <option value="low_risk_auto">允许低风险自动执行</option>
            </select>
          </label>
          <label>
            每日上限
            <select
              value={proactive.preferences.daily_limit}
              onChange={(event) => { void setPreferences({ daily_limit: Number(event.target.value) }); }}
            >
              {[1, 3, 5, 10].map((value) => <option key={value} value={value}>{value} 条</option>)}
            </select>
          </label>
          <label>
            <input
              type="checkbox"
              checked={proactive.preferences.quiet_hours.enabled}
              onChange={(event) => { void setPreferences({ quiet_hours: { ...proactive.preferences.quiet_hours, enabled: event.target.checked } }); }}
            />
            22:00–08:00 免打扰
          </label>
          <Button size="small" variant="text" loading={mutating === 'tick'} onClick={() => { void run('tick', 'tick'); }}>
            立即检查
          </Button>
          {typeof Notification !== 'undefined' && Notification.permission !== 'granted' && (
            <Button size="small" variant="text" onClick={() => { void Notification.requestPermission(); }}>
              开启系统通知
            </Button>
          )}
        </div>
      )}

      {pendingWorkflows.map((workflow) => (
        <div className="proactive-workflow" key={workflow.id}>
          <strong>工作流提案：{workflow.title}</strong>
          <span>{workflow.reason}</span>
          <small>{workflow.steps.length} 个步骤；确认后才会后台执行</small>
          <div className="proactive-actions">
            <Button size="small" theme="primary" loading={mutating === `workflow:${workflow.id}`} onClick={() => { void run(`workflow:${workflow.id}`, 'confirm_workflow', { workflow_id: workflow.id, version: workflow.version }); }}>
              确认启用
            </Button>
            <Button size="small" variant="text" onClick={() => { void run(`workflow:${workflow.id}`, 'reject_workflow', { workflow_id: workflow.id, version: workflow.version }); }}>
              拒绝
            </Button>
          </div>
        </div>
      ))}
      {activeWorkflows.map((workflow) => (
        <div className="proactive-workflow is-active" key={workflow.id}>
          <strong>运行中：{workflow.title}</strong>
          <small>{workflow.steps.filter((step) => step.status === 'completed' || step.status === 'skipped').length}/{workflow.steps.length} 个步骤已处理</small>
          <div className="proactive-actions">
            <Button size="small" variant="text" onClick={() => { void run(`workflow:${workflow.id}`, 'cancel_workflow', { workflow_id: workflow.id, version: workflow.version }); }}>
              停止工作流
            </Button>
          </div>
        </div>
      ))}

      {!notifications.length && (
        <div className="proactive-empty">
          {proactive?.last_tick ? '最近一次检查未发现需要提醒的事项' : '等待后台首次检查日程'}
        </div>
      )}
      {notifications.map((notification) => (
        <div className={`proactive-nudge priority-${notification.priority}`} key={notification.id}>
          <div className="proactive-nudge-heading">
            <strong>{notification.title}</strong>
            {notification.status === 'snoozed' && <span>稍后至 {clock(notification.snoozed_until)}</span>}
          </div>
          <span>{notification.body}</span>
          <small>原因：{notification.reason}</small>
          <div className="proactive-actions">
            <Button size="small" variant="text" onClick={() => { void fillDraft(notification.id, notification.action_prompt); }}>
              放入输入栏
            </Button>
            <Button size="small" variant="text" loading={mutating === `snooze:${notification.id}`} onClick={() => { void run(`snooze:${notification.id}`, 'snooze', { notification_id: notification.id, until: Math.floor(Date.now() / 1000) + 3600 }); }}>
              1小时后
            </Button>
            <Button size="small" variant="text" loading={mutating === `dismiss:${notification.id}`} onClick={() => { void run(`dismiss:${notification.id}`, 'dismiss', { notification_id: notification.id }); }}>
              忽略
            </Button>
            {typeof notification.evidence.workflow_id === 'string' && typeof notification.evidence.step_id === 'string' && notification.evidence.workflow_phase !== 'compensation' && notification.evidence.workflow_phase !== 'failure' && (
              <>
                <Button size="small" theme="success" loading={mutating === `step:${notification.id}`} onClick={() => { void run(`step:${notification.id}`, 'complete_workflow_step', { workflow_id: notification.evidence.workflow_id, step_id: notification.evidence.step_id }); }}>
                  完成步骤
                </Button>
                <Button size="small" variant="text" loading={mutating === `fail:${notification.id}`} onClick={() => { void run(`fail:${notification.id}`, 'fail_workflow_step', { workflow_id: notification.evidence.workflow_id, step_id: notification.evidence.step_id }); }}>
                  标记失败
                </Button>
              </>
            )}
            {typeof notification.evidence.workflow_id === 'string' && typeof notification.evidence.step_id === 'string' && (notification.evidence.workflow_phase === 'compensation' || notification.evidence.workflow_phase === 'failure') && (
              <>
                {notification.evidence.workflow_phase === 'compensation' && (
                  <Button size="small" theme="success" loading={mutating === `compensate:${notification.id}`} onClick={() => { void run(`compensate:${notification.id}`, 'compensate_workflow_step', { workflow_id: notification.evidence.workflow_id, step_id: notification.evidence.step_id }); }}>
                    补偿已完成
                  </Button>
                )}
                <Button size="small" variant="outline" loading={mutating === `retry:${notification.id}`} onClick={() => { void run(`retry:${notification.id}`, 'retry_workflow_step', { workflow_id: notification.evidence.workflow_id, step_id: notification.evidence.step_id }); }}>
                  重试步骤
                </Button>
              </>
            )}
          </div>
        </div>
      ))}
      {showRuns && (
        <div className="proactive-runs">
          {(proactive?.runs || []).slice(0, 10).map((item) => (
            <div key={item.id}>
              <span>{item.intent}</span>
              <span>{item.status}{item.reason ? ` · ${item.reason}` : ''}</span>
              <time>{clock(item.updated_at)}</time>
            </div>
          ))}
          {!proactive?.runs?.length && <span>暂无后台运行记录</span>}
        </div>
      )}
      {proactive?.last_tick && (
        <div className="proactive-last-scan">最近检查：{clock(proactive.last_tick.finished_at)}</div>
      )}
    </div>
  );
}
