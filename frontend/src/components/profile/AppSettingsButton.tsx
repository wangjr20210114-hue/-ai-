import { useEffect, useState } from 'react';
import { Button, Dialog, MessagePlugin } from 'tdesign-react';
import { SettingIcon } from 'tdesign-icons-react';
import { useAppDispatch, useAppState } from '../../store/appState';
import { proactiveOperation } from '../../services/api';
import { getReadingLibrary, updateReadingSettings } from '../../services/paperApi';
import AgentIntelligencePanel from './AgentIntelligencePanel';

export default function AppSettingsButton() {
  const { conversationId, proactive } = useAppState();
  const dispatch = useAppDispatch();
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState('');
  const [automatic, setAutomatic] = useState(true);

  useEffect(() => {
    if (!visible) return;
    void Promise.all([
      proactiveOperation(conversationId, 'refresh').then((next) => dispatch({ type: 'HYDRATE_PROACTIVE', payload: next })),
      getReadingLibrary().then((data) => setAutomatic(data.settings.auto_organize)),
    ]).catch((error) => console.warn('settings refresh failed', error));
  }, [conversationId, dispatch, visible]);

  const setPreferences = async (changes: Record<string, unknown>) => {
    setBusy('proactive');
    try {
      const next = await proactiveOperation(conversationId, 'update_preferences', {
        preferences: { ...(proactive?.preferences || {}), ...changes },
      });
      dispatch({ type: 'HYDRATE_PROACTIVE', payload: next });
      MessagePlugin.success('主动服务设置已保存');
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : '保存主动服务设置失败');
    } finally { setBusy(''); }
  };

  const saveReading = async (value: boolean) => {
    setAutomatic(value);
    setBusy('reading');
    try {
      await updateReadingSettings(value);
      MessagePlugin.success(value ? '已开启阅读库自动整理' : '已切换为手动整理');
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : '保存阅读设置失败');
    } finally { setBusy(''); }
  };

  const preferences = proactive?.preferences;
  return <>
    <Button className="sidebar-settings-button" block variant="text" icon={<SettingIcon />} onClick={() => setVisible(true)}>设置</Button>
    <Dialog
      visible={visible}
      header="元宝设置"
      width={720}
      footer={false}
      onClose={() => setVisible(false)}
      onCancel={() => setVisible(false)}
    >
      <div className="app-settings-dialog">
        <section className="app-settings-section">
          <h3>主动式服务</h3>
          <p>在打开空白新对话、日程或路线发生变化时重新检查；有重要事项时由大模型在新对话里自然提醒。</p>
          {preferences && <div className="app-settings-grid">
            <label><span>启用主动服务</span><input type="checkbox" checked={preferences.enabled !== false} disabled={busy === 'proactive'} onChange={(event) => void setPreferences({ enabled: event.target.checked })} /></label>
            <label><span>主动权限</span><select value={preferences.autonomy_mode} disabled={busy === 'proactive'} onChange={(event) => void setPreferences({ autonomy_mode: event.target.value })}><option value="observe">仅观察</option><option value="remind">可提醒</option><option value="propose">可提案</option><option value="low_risk_auto">允许低风险自动执行</option></select></label>
            <label><span>每日提醒上限</span><select value={preferences.daily_limit} disabled={busy === 'proactive'} onChange={(event) => void setPreferences({ daily_limit: Number(event.target.value) })}>{[1, 3, 5, 10].map((value) => <option key={value} value={value}>{value} 条</option>)}</select></label>
            <label><span>关注未来范围</span><select value={preferences.lookahead_hours} disabled={busy === 'proactive'} onChange={(event) => void setPreferences({ lookahead_hours: Number(event.target.value) })}><option value={12}>未来 12 小时</option><option value={24}>未来 24 小时</option><option value={48}>未来 48 小时</option><option value={72}>未来 3 天</option></select></label>
            <label><span>22:00–08:00 免打扰</span><input type="checkbox" checked={preferences.quiet_hours.enabled} disabled={busy === 'proactive'} onChange={(event) => void setPreferences({ quiet_hours: { ...preferences.quiet_hours, enabled: event.target.checked } })} /></label>
            <Button size="small" variant="outline" loading={busy === 'scan'} onClick={() => {
              setBusy('scan');
              void proactiveOperation(conversationId, 'refresh').then((next) => {
                dispatch({ type: 'HYDRATE_PROACTIVE', payload: next });
                MessagePlugin.success('已检查最新日程、天气与路线');
              }).catch((error) => MessagePlugin.error(error instanceof Error ? error.message : '检查失败')).finally(() => setBusy(''));
            }}>立即检查</Button>
          </div>}
          <details className="proactive-settings-runs">
            <summary>运行记录与诊断</summary>
            <p>最近检查：{proactive?.last_tick?.finished_at ? new Date(proactive.last_tick.finished_at * 1000).toLocaleString('zh-CN') : '尚未检查'}</p>
            <div>
              {(proactive?.runs || []).slice(0, 12).map((run) => <div key={run.id}><span>{run.intent}</span><b>{run.status}</b><small>{run.reason || run.trigger_origin}</small></div>)}
              {!proactive?.runs?.length && <span>暂无运行记录</span>}
            </div>
          </details>
        </section>

        <AgentIntelligencePanel embedded />

        <section className="app-settings-section">
          <h3>阅读库整理</h3>
          <label className="app-settings-choice"><input type="radio" checked={automatic} disabled={busy === 'reading'} onChange={() => void saveReading(true)} /><span><strong>自动整理</strong><small>按论文、报告、手册等类型自动归档。</small></span></label>
          <label className="app-settings-choice"><input type="radio" checked={!automatic} disabled={busy === 'reading'} onChange={() => void saveReading(false)} /><span><strong>手动整理</strong><small>新文档先进入未分类。</small></span></label>
        </section>
      </div>
    </Dialog>
  </>;
}
