import { useCallback, useEffect, useState } from 'react';
import { Button, MessagePlugin, Tag } from 'tdesign-react';
import {
  deleteAgentMemory,
  exportAgentMemories,
  getUsageSummary,
  listAgentMemories,
  updateUsagePreferences,
} from '../../services/api';
import type { AgentMemory, UsageSummary } from '../../types';

function renderValue(value: unknown) {
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

/** User-controlled memory and budget management. */
export default function AgentIntelligencePanel() {
  const [memories, setMemories] = useState<AgentMemory[]>([]);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [dailyBudget, setDailyBudget] = useState('20');
  const [monthlyBudget, setMonthlyBudget] = useState('300');
  const [enforcement, setEnforcement] = useState<'off' | 'soft' | 'hard'>('soft');
  const [busyId, setBusyId] = useState('');

  const refresh = useCallback(async () => {
    try {
      const [nextMemories, nextUsage] = await Promise.all([
        listAgentMemories(),
        getUsageSummary(),
      ]);
      setMemories(nextMemories);
      setUsage(nextUsage);
      setDailyBudget(String(nextUsage.preferences.daily_budget_cny));
      setMonthlyBudget(String(nextUsage.preferences.monthly_budget_cny));
      setEnforcement(nextUsage.preferences.enforcement);
    } catch (error) {
      console.warn('Agent intelligence refresh failed', error);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const removeMemory = async (memory: AgentMemory) => {
    setBusyId(memory.id);
    try {
      await deleteAgentMemory(memory.id);
      MessagePlugin.success('记忆已删除');
      await refresh();
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : '删除失败');
    } finally {
      setBusyId('');
    }
  };

  const exportMemories = async () => {
    try {
      const data = await exportAgentMemories();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `agent-memories-${new Date().toISOString().slice(0, 10)}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : '导出失败');
    }
  };

  const saveBudget = async () => {
    const daily = Number(dailyBudget);
    const monthly = Number(monthlyBudget);
    if (!Number.isFinite(daily) || !Number.isFinite(monthly) || daily < 0 || monthly < 0) {
      MessagePlugin.warning('预算必须是非负数字');
      return;
    }
    try {
      await updateUsagePreferences({
        daily_budget_cny: daily,
        monthly_budget_cny: monthly,
        enforcement,
      });
      MessagePlugin.success('预算设置已保存');
      await refresh();
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : '预算保存失败');
    }
  };

  return (
    <div className="my-panel-card" data-testid="agent-intelligence-panel">
      <div className="section-title" style={{ marginBottom: 8 }}>
        <span style={{ marginRight: 6 }}>🧠</span>
        记忆与预算
        <Tag size="small" variant="light" style={{ marginLeft: 'auto' }}>
          {memories.length} 条记忆
        </Tag>
      </div>

      <details>
        <summary style={{ fontSize: 11.5, cursor: 'pointer' }}>长期记忆（{memories.length}）</summary>
        <div style={{ marginTop: 6 }}>
          {memories.length === 0 ? (
            <div style={{ fontSize: 11, color: 'var(--app-text-3)' }}>暂无记忆。系统会在对话中自动提取并更新你的偏好和事实。</div>
          ) : memories.map((memory) => (
            <div key={memory.id} style={{ padding: '6px 0', borderBottom: '1px solid var(--app-border)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                <strong style={{ fontSize: 11 }}>{memory.memory_key}</strong>
                <Tag size="small" variant="light">v{memory.version}</Tag>
                {memory.sensitivity !== 'normal' ? <Tag size="small" theme="warning">敏感</Tag> : null}
                <Button size="small" variant="text" style={{ marginLeft: 'auto' }} loading={busyId === memory.id} onClick={() => { void removeMemory(memory); }}>
                  删除
                </Button>
              </div>
              <pre style={{ margin: '2px 0', whiteSpace: 'pre-wrap', fontSize: 10.5, color: 'var(--app-text-2)' }}>
                {renderValue(memory.value_json)}
              </pre>
            </div>
          ))}
          <Button size="small" variant="outline" style={{ marginTop: 6 }} onClick={() => { void exportMemories(); }}>
            导出 JSON
          </Button>
        </div>
      </details>

      <details style={{ marginTop: 8 }}>
        <summary style={{ fontSize: 11.5, cursor: 'pointer' }}>使用与预算</summary>
        <div style={{ marginTop: 6, fontSize: 11, color: 'var(--app-text-2)' }}>
          今日 ¥{Number(usage?.daily.estimated_cost || 0).toFixed(4)} / 本月 ¥{Number(usage?.monthly.estimated_cost || 0).toFixed(4)}
          {usage?.alerts.daily || usage?.alerts.monthly ? <Tag size="small" theme="warning" style={{ marginLeft: 5 }}>接近预算</Tag> : null}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 5, marginTop: 6 }}>
          <label style={{ fontSize: 10.5 }}>
            日预算
            <input value={dailyBudget} onChange={(event) => setDailyBudget(event.target.value)} inputMode="decimal" style={{ width: '100%', boxSizing: 'border-box' }} />
          </label>
          <label style={{ fontSize: 10.5 }}>
            月预算
            <input value={monthlyBudget} onChange={(event) => setMonthlyBudget(event.target.value)} inputMode="decimal" style={{ width: '100%', boxSizing: 'border-box' }} />
          </label>
        </div>
        <label style={{ display: 'block', fontSize: 10.5, marginTop: 5 }}>
          超限策略
          <select value={enforcement} onChange={(event) => setEnforcement(event.target.value as 'off' | 'soft' | 'hard')} style={{ marginLeft: 6 }}>
            <option value="off">仅记录</option>
            <option value="soft">提示并要求确认</option>
            <option value="hard">阻止执行</option>
          </select>
        </label>
        <Button size="small" theme="primary" style={{ marginTop: 6 }} onClick={() => { void saveBudget(); }}>保存预算</Button>
      </details>
    </div>
  );
}
