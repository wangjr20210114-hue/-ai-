import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Dialog, MessagePlugin, Tag } from 'tdesign-react';
import { AppIcon } from 'tdesign-icons-react';
import { useAppState } from '../../store/appState';
import { skillsOperation } from '../../services/api';
import { SKILLS_CATALOG, SKILL_NAME } from './skillsCatalog';

export default function SkillsMarketplaceButton() {
  const { conversationId } = useAppState();
  const [visible, setVisible] = useState(false);
  const [preferences, setPreferences] = useState<Record<string, boolean>>({});
  const [meetingConfigured, setMeetingConfigured] = useState(false);
  const [loading, setLoading] = useState(false);
  const [savingId, setSavingId] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const result = await skillsOperation(conversationId);
      setPreferences(result.preferences);
      setMeetingConfigured(result.providers.meeting);
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : '读取 Skills 状态失败');
    } finally { setLoading(false); }
  }, [conversationId]);

  useEffect(() => { if (visible) void refresh(); }, [refresh, visible]);
  useEffect(() => {
    const open = () => setVisible(true);
    window.addEventListener('yuanbao:open-skills', open);
    return () => window.removeEventListener('yuanbao:open-skills', open);
  }, []);

  const enabledCount = useMemo(
    () => SKILLS_CATALOG.filter((skill) => skill.locked || preferences[skill.id] !== false).length,
    [preferences],
  );

  const save = async (skillId: string, enabled: boolean) => {
    const skill = SKILLS_CATALOG.find((item) => item.id === skillId);
    if (!skill || skill.locked) return;
    const next = { ...preferences, [skillId]: enabled };
    const autoEnabled = enabled
      ? (skill.requires || []).filter((dependency) => next[dependency] === false)
      : [];
    autoEnabled.forEach((dependency) => { next[dependency] = true; });
    setSavingId(skillId);
    try {
      const result = await skillsOperation(conversationId, next);
      setPreferences(result.preferences);
      setMeetingConfigured(result.providers.meeting);
      window.dispatchEvent(new CustomEvent('yuanbao:skills-changed', { detail: result.preferences }));
      if (autoEnabled.length) {
        MessagePlugin.success(`已同时开启必要依赖：${autoEnabled.map((id) => SKILL_NAME[id]).join('、')}`);
      } else {
        MessagePlugin.success(`${skill.name}已${enabled ? '开启' : '关闭'}`);
      }
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : 'Skills 设置保存失败');
    } finally { setSavingId(''); }
  };

  return <>
    <Button className="sidebar-settings-button" block variant="text" icon={<AppIcon />} onClick={() => setVisible(true)}>Skills 广场</Button>
    <Dialog visible={visible} header="Skills 广场" width={760} footer={false} onClose={() => setVisible(false)} onCancel={() => setVisible(false)}>
      <div className="skills-marketplace-head">
        <div><strong>组合你的元宝能力</strong><span>现有能力默认开启，设置保存在 Makers 原生存储中。</span></div>
        <Tag theme="primary" variant="light">已开启 {enabledCount}/{SKILLS_CATALOG.length}</Tag>
      </div>
      <div className="skills-marketplace" aria-busy={loading}>
        {SKILLS_CATALOG.map((skill) => {
          const enabled = skill.locked || preferences[skill.id] !== false;
          const missingRecommended = (skill.recommends || []).filter((id) => preferences[id] === false);
          const missingRequired = (skill.requires || []).filter((id) => preferences[id] === false);
          const blocked = enabled && missingRequired.length > 0;
          const connected = skill.id !== 'tencent-meeting' || meetingConfigured;
          return <article className={`skill-market-card ${enabled ? 'is-enabled' : 'is-disabled'}`} key={skill.id}>
            <div className="skill-market-icon" aria-hidden="true">{skill.icon}</div>
            <div className="skill-market-content">
              <div className="skill-market-title">
                <strong>{skill.name}</strong>
                {skill.locked && <Tag size="small">核心</Tag>}
                {skill.external && <Tag size="small" theme={connected ? 'success' : 'warning'}>{connected ? '已连接' : '待连接'}</Tag>}
              </div>
              <p>{skill.description}</p>
              {blocked && <div className="skill-dependency-note is-blocked">需要先开启：{missingRequired.map((id) => SKILL_NAME[id]).join('、')}</div>}
              {!blocked && enabled && missingRecommended.length > 0 && <div className="skill-dependency-note">建议同时开启 {missingRecommended.map((id) => SKILL_NAME[id]).join('、')}，可获得完整联动。</div>}
              {skill.id === 'calendar' && preferences.maps === false && enabled && <div className="skill-dependency-note">日程仍可使用；涉及真实地点时，AI 会建议开启地图，而不会编造地址。</div>}
              {skill.id === 'tencent-meeting' && !meetingConfigured && <button className="skill-install-link" type="button" onClick={() => window.open('https://meeting.tencent.com/ai-skill', '_blank', 'noopener,noreferrer')}>连接腾讯会议个人 Skill →</button>}
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={enabled}
              aria-label={`${enabled ? '关闭' : '开启'}${skill.name}`}
              className={`skill-toggle ${enabled ? 'is-on' : ''}`}
              disabled={skill.locked || savingId === skill.id}
              onClick={() => void save(skill.id, !enabled)}
            ><span /></button>
          </article>;
        })}
        {!SKILLS_CATALOG.length && !loading && <div className="conversation-list-empty">暂无可用 Skill</div>}
      </div>
      <div className="skills-marketplace-footer">
        <span>关闭能力后，AI 会明确说明限制，并引导你按需重新开启。</span>
        <Button variant="outline" loading={loading} onClick={() => void refresh()}>刷新状态</Button>
      </div>
    </Dialog>
  </>;
}
