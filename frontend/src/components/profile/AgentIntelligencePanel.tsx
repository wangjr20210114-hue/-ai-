import { useCallback, useEffect, useState } from 'react';
import { Button, MessagePlugin, Tag } from 'tdesign-react';
import { useAppState } from '../../store/appState';
import { intelligenceOperation } from '../../services/api';
import type { MakersIntelligenceState } from '../../types';
import { revokeConnectorSecret, rotateConnectorSecret } from '../../services/auth';
import { useSession } from '../auth/session';

function renderValue(value: unknown) {
  if (typeof value === 'string') return value;
  try { return JSON.stringify(value, null, 2); } catch { return String(value); }
}

export default function AgentIntelligencePanel() {
  const { conversationId } = useAppState();
  const session = useSession();
  const [state, setState] = useState<MakersIntelligenceState | null>(null);
  const [busy, setBusy] = useState('');
  const [dailyLimit, setDailyLimit] = useState('250000');
  const [monthlyLimit, setMonthlyLimit] = useState('3000000');
  const [enforcement, setEnforcement] = useState<'off' | 'soft' | 'hard'>('soft');
  const [connectorSecret, setConnectorSecret] = useState('');
  const refresh = useCallback(async () => {
    try {
      const next = await intelligenceOperation(conversationId);
      setState(next);
      setDailyLimit(String(next.usage.preferences.daily_token_limit));
      setMonthlyLimit(String(next.usage.preferences.monthly_token_limit));
      setEnforcement(next.usage.preferences.enforcement);
    }
    catch (error) { console.warn('intelligence refresh failed', error); }
  }, [conversationId]);
  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => { void refresh(); }, 60_000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const mutate = async (key: string, operation: string, input: Record<string, unknown>) => {
    setBusy(key);
    try { setState(await intelligenceOperation(conversationId, operation, input)); }
    catch (error) { MessagePlugin.error(error instanceof Error ? error.message : '操作失败'); }
    finally { setBusy(''); }
  };
  const pendingMemories = (state?.memory_proposals || []).filter((item) => item.status === 'pending');
  const pendingRules = (state?.rule_proposals || []).filter((item) => item.status === 'pending');

  return (
    <div className="my-panel-card intelligence-card">
      <details>
        <summary className="section-title">
          <span>🧠 记忆与学习</span>
          <Tag size="small" variant="light">{state?.memories.length || 0}</Tag>
        </summary>
        <div className="intelligence-content">
          {pendingMemories.map((proposal) => (
            <div className="intelligence-proposal" key={proposal.id}>
              <strong>待确认记忆：{proposal.memory_key}</strong>
              <pre>{renderValue(proposal.value)}</pre>
              <small>{proposal.reason}{proposal.sensitivity === 'sensitive' ? ' · 敏感' : ''}</small>
              <div>
                <Button size="small" variant="text" loading={busy === `confirm:${proposal.id}`} onClick={() => { void mutate(`confirm:${proposal.id}`, 'confirm_memory', { proposal_id: proposal.id, version: proposal.version }); }}>确认</Button>
                <Button size="small" variant="text" onClick={() => { void mutate(`reject:${proposal.id}`, 'reject_memory', { proposal_id: proposal.id, version: proposal.version }); }}>拒绝</Button>
              </div>
            </div>
          ))}
          {pendingRules.map((rule) => (
            <div className="intelligence-proposal" key={rule.id}>
              <strong>规则建议</strong><span>{rule.reason}</span>
              <div>
                <Button size="small" variant="text" onClick={() => { void mutate(`rule:${rule.id}`, 'confirm_rule', { rule_id: rule.id, version: rule.version }); }}>采用</Button>
                <Button size="small" variant="text" onClick={() => { void mutate(`rule:${rule.id}`, 'reject_rule', { rule_id: rule.id, version: rule.version }); }}>不采用</Button>
              </div>
            </div>
          ))}
          {(state?.memories || []).map((memory) => (
            <div className="intelligence-memory" key={memory.id}>
              <strong>{memory.memory_key} <small>v{memory.version}</small></strong>
              <pre>{renderValue(memory.value)}</pre>
              {memory.history && memory.history.length > 0 && (
                <Button size="small" variant="text" onClick={() => {
                  const previous = memory.history?.[memory.history.length - 1];
                  if (previous) void mutate(`rollback:${memory.id}`, 'rollback_memory', { memory_id: memory.id, target_version: previous.version });
                }}>回滚上一版</Button>
              )}
              <Button size="small" variant="text" onClick={() => { void mutate(`delete:${memory.id}`, 'delete_memory', { memory_id: memory.id }); }}>删除</Button>
            </div>
          ))}
          {!pendingMemories.length && !pendingRules.length && !state?.memories.length && <div className="proactive-empty">暂无已确认记忆或待处理提案</div>}
          {state?.usage && (
            <div className="intelligence-usage">
              今日 {state.usage.daily_tokens.toLocaleString()} tokens · 本月 {state.usage.monthly_tokens.toLocaleString()}
              {(state.usage.alerts.daily || state.usage.alerts.monthly) && <Tag size="small" theme="warning">达到预算</Tag>}
            </div>
          )}
          <details className="intelligence-budget">
            <summary>Token 预算</summary>
            <label>每日<input inputMode="numeric" value={dailyLimit} onChange={(event) => setDailyLimit(event.target.value)} /></label>
            <label>每月<input inputMode="numeric" value={monthlyLimit} onChange={(event) => setMonthlyLimit(event.target.value)} /></label>
            <label>策略<select value={enforcement} onChange={(event) => setEnforcement(event.target.value as 'off' | 'soft' | 'hard')}><option value="off">仅记录</option><option value="soft">提醒</option><option value="hard">阻止</option></select></label>
            <Button size="small" variant="text" onClick={() => { void mutate('budget', 'update_usage_preferences', { preferences: { daily_token_limit: Number(dailyLimit), monthly_token_limit: Number(monthlyLimit), enforcement } }); }}>保存预算</Button>
          </details>
          {session?.mode === 'multi_user' && (
            <details className="intelligence-budget">
              <summary>外部信号连接器</summary>
              <p>为日历、邮件或企业消息 webhook 生成用户级密钥。新密钥仅显示一次，轮换会立即撤销旧密钥。</p>
              {connectorSecret && <code className="connector-secret">{connectorSecret}</code>}
              <div>
                <Button size="small" variant="text" onClick={async () => {
                  try { setConnectorSecret(await rotateConnectorSecret()); MessagePlugin.success('已轮换连接器密钥'); }
                  catch (error) { MessagePlugin.error(error instanceof Error ? error.message : '操作失败'); }
                }}>生成/轮换</Button>
                <Button size="small" variant="text" onClick={async () => {
                  try { await revokeConnectorSecret(); setConnectorSecret(''); MessagePlugin.success('已撤销连接器密钥'); }
                  catch (error) { MessagePlugin.error(error instanceof Error ? error.message : '操作失败'); }
                }}>撤销</Button>
              </div>
            </details>
          )}
        </div>
      </details>
    </div>
  );
}
