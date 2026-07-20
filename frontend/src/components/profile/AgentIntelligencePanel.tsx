import { useCallback, useEffect, useState } from 'react';
import { Button, MessagePlugin, Tag } from 'tdesign-react';
import { useAppState } from '../../store/appState';
import { intelligenceOperation } from '../../services/api';
import type { MakersIntelligenceState } from '../../types';

export default function AgentIntelligencePanel() {
  const { conversationId } = useAppState();
  const [state, setState] = useState<MakersIntelligenceState | null>(null);
  const [busy, setBusy] = useState('');
  const [dailyLimit, setDailyLimit] = useState('250000');
  const [monthlyLimit, setMonthlyLimit] = useState('3000000');
  const [enforcement, setEnforcement] = useState<'off' | 'soft' | 'hard'>('soft');
  const [resultLimit, setResultLimit] = useState(8);
  const [imageLimit, setImageLimit] = useState(2);
  const [parallelImageSearch, setParallelImageSearch] = useState(true);
  const refresh = useCallback(async () => {
    try {
      const next = await intelligenceOperation(conversationId);
      setState(next);
      setDailyLimit(String(next.usage.preferences.daily_token_limit));
      setMonthlyLimit(String(next.usage.preferences.monthly_token_limit));
      setEnforcement(next.usage.preferences.enforcement);
      setResultLimit(next.search_preferences?.result_limit ?? 8);
      setImageLimit(next.search_preferences?.image_limit ?? 2);
      setParallelImageSearch(next.search_preferences?.parallel_image_search ?? true);
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
  const pendingRules = (state?.rule_proposals || []).filter((item) => item.status === 'pending');

  return (
    <div className="my-panel-card intelligence-card">
      <details>
        <summary className="section-title">
          <span>🧠 主动策略与预算</span>
        </summary>
        <div className="intelligence-content">
          {pendingRules.map((rule) => (
            <div className="intelligence-proposal" key={rule.id}>
              <strong>规则建议</strong><span>{rule.reason}</span>
              <div>
                <Button size="small" variant="text" onClick={() => { void mutate(`rule:${rule.id}`, 'confirm_rule', { rule_id: rule.id, version: rule.version }); }}>采用</Button>
                <Button size="small" variant="text" onClick={() => { void mutate(`rule:${rule.id}`, 'reject_rule', { rule_id: rule.id, version: rule.version }); }}>不采用</Button>
              </div>
            </div>
          ))}
          {!pendingRules.length && <div className="proactive-empty">暂无待处理的主动策略建议</div>}
          <details className="intelligence-budget">
            <summary>自动记忆控制</summary>
            <p>记忆内容由后台自动过滤和维护，不在页面展示。</p>
            <label><input type="checkbox" disabled={busy === 'memory-enabled'} checked={state?.memory_preferences?.enabled ?? true} onChange={(event) => {
              void mutate('memory-enabled', 'update_memory_preferences', { preferences: { enabled: event.target.checked } });
            }} />启用自动记忆</label>
            <Button size="small" variant="text" theme="danger" loading={busy === 'clear-memory'} onClick={() => {
              if (window.confirm('确定清除全部自动记忆吗？此操作不会删除聊天记录。')) {
                void mutate('clear-memory', 'clear_memories', {});
              }
            }}>清除全部自动记忆</Button>
          </details>
          {state?.usage && (
            <div className="intelligence-usage">
              今日 {state.usage.daily_tokens.toLocaleString()} tokens · 本月 {state.usage.monthly_tokens.toLocaleString()}
              {(state.usage.alerts.daily || state.usage.alerts.monthly) && <Tag size="small" theme="warning">达到预算</Tag>}
            </div>
          )}
          <details className="intelligence-budget">
            <summary>联网搜索设置</summary>
            <p>推荐值兼顾速度与答案质量。新闻等适合配图的问题仍由 LLM 规划是否检索图片。</p>
            <label>网页结果上限<select value={resultLimit} onChange={(event) => setResultLimit(Number(event.target.value))}><option value={4}>4（最快）</option><option value={8}>8（推荐）</option><option value={12}>12</option><option value={18}>18（最完整）</option></select></label>
            <label>回答图片上限<select value={imageLimit} onChange={(event) => setImageLimit(Number(event.target.value))}><option value={0}>0（关闭配图）</option><option value={2}>2（推荐）</option><option value={4}>4</option></select></label>
            <label><input type="checkbox" checked={parallelImageSearch} onChange={(event) => setParallelImageSearch(event.target.checked)} />事实与图片查询并行（推荐）</label>
            <Button size="small" variant="text" loading={busy === 'search'} onClick={() => { void mutate('search', 'update_search_preferences', { preferences: { result_limit: resultLimit, image_limit: imageLimit, parallel_image_search: parallelImageSearch } }); }}>保存搜索设置</Button>
          </details>
          <details className="intelligence-budget">
            <summary>Token 预算</summary>
            <label>每日<input inputMode="numeric" value={dailyLimit} onChange={(event) => setDailyLimit(event.target.value)} /></label>
            <label>每月<input inputMode="numeric" value={monthlyLimit} onChange={(event) => setMonthlyLimit(event.target.value)} /></label>
            <label>策略<select value={enforcement} onChange={(event) => setEnforcement(event.target.value as 'off' | 'soft' | 'hard')}><option value="off">仅记录</option><option value="soft">提醒</option><option value="hard">阻止</option></select></label>
            <Button size="small" variant="text" onClick={() => { void mutate('budget', 'update_usage_preferences', { preferences: { daily_token_limit: Number(dailyLimit), monthly_token_limit: Number(monthlyLimit), enforcement } }); }}>保存预算</Button>
          </details>
        </div>
      </details>
    </div>
  );
}
