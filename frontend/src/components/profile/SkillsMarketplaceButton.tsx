import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Dialog, MessagePlugin, Tag } from 'tdesign-react';
import { AppIcon } from 'tdesign-icons-react';
import { useAppState } from '../../store/appState';
import { skillsOperation } from '../../services/api';
import { SKILLS_CATALOG } from './skillsCatalog';
import { useLanguage } from '../../i18n';

export default function SkillsMarketplaceButton() {
  const { conversationId } = useAppState();
  const { t } = useLanguage();
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
      MessagePlugin.error(error instanceof Error ? error.message : t('skillsReadFailed'));
    } finally { setLoading(false); }
  }, [conversationId, t]);

  useEffect(() => { if (visible) void refresh(); }, [refresh, visible]);
  useEffect(() => {
    const open = () => {
      setLoading(true);
      setVisible(true);
    };
    window.addEventListener('yuanbao:open-skills', open);
    return () => window.removeEventListener('yuanbao:open-skills', open);
  }, []);

  const enabledCount = useMemo(
    () => SKILLS_CATALOG.filter((skill) => skill.locked || preferences[skill.id] !== false).length,
    [preferences],
  );
  const openMarketplace = () => {
    setLoading(true);
    setVisible(true);
  };

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
        MessagePlugin.success(t('skillsDependenciesEnabled', { names: autoEnabled.map((id) => {
          const dependency = SKILLS_CATALOG.find((item) => item.id === id);
          return dependency ? t(dependency.nameKey) : id;
        }).join('、') }));
      } else {
        MessagePlugin.success(t('skillStateChanged', { name: t(skill.nameKey), state: enabled ? t('enabled') : t('disabled') }));
      }
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : t('skillsSaveFailed'));
    } finally { setSavingId(''); }
  };

  return <>
    <Button className="sidebar-settings-button" block variant="text" icon={<AppIcon />} onClick={openMarketplace}>{t('skillsMarketplace')}</Button>
    <Dialog
      visible={visible}
      header={t('skillsMarketplace')}
      width={760}
      placement="center"
      dialogClassName="secondary-dialog skills-marketplace-modal"
      footer={false}
      onClose={() => setVisible(false)}
      onCancel={() => setVisible(false)}
    >
      <div className="skills-marketplace-head">
        <div><strong>{t('composeSkills')}</strong><span>{t('skillsStoredNatively')}</span></div>
        <Tag theme="primary" variant="light">{loading ? t('loading') : t('enabledCount', { enabled: enabledCount, total: SKILLS_CATALOG.length })}</Tag>
      </div>
      <div className="skills-marketplace" aria-busy={loading}>
        {loading ? Array.from({ length: 6 }, (_, index) => (
          <div className="skill-market-skeleton" key={`skill-loading-${index}`} aria-hidden="true">
            <span /><div><i /><i /></div>
          </div>
        )) : SKILLS_CATALOG.map((skill) => {
          const enabled = skill.locked || preferences[skill.id] !== false;
          const missingRecommended = (skill.recommends || []).filter((id) => preferences[id] === false);
          const missingRequired = (skill.requires || []).filter((id) => preferences[id] === false);
          const blocked = enabled && missingRequired.length > 0;
          const connected = skill.id !== 'tencent-meeting' || meetingConfigured;
          return <article className={`skill-market-card ${enabled ? 'is-enabled' : 'is-disabled'}`} key={skill.id}>
            <div className="skill-market-icon" aria-hidden="true">{skill.icon}</div>
            <div className="skill-market-content">
              <div className="skill-market-title">
                <strong>{t(skill.nameKey)}</strong>
                {skill.locked && <Tag size="small">{t('core')}</Tag>}
                {skill.external && <Tag size="small" theme={connected ? 'success' : 'warning'}>{connected ? t('connected') : t('waitingConnection')}</Tag>}
              </div>
              <p>{t(skill.descriptionKey)}</p>
              {blocked && <div className="skill-dependency-note is-blocked">{t('requiresSkills', { names: missingRequired.map((id) => {
                const dependency = SKILLS_CATALOG.find((item) => item.id === id);
                return dependency ? t(dependency.nameKey) : id;
              }).join('、') })}</div>}
              {!blocked && enabled && missingRecommended.length > 0 && <div className="skill-dependency-note">{t('recommendsSkills', { names: missingRecommended.map((id) => {
                const dependency = SKILLS_CATALOG.find((item) => item.id === id);
                return dependency ? t(dependency.nameKey) : id;
              }).join('、') })}</div>}
              {skill.id === 'calendar' && preferences.maps === false && enabled && <div className="skill-dependency-note">{t('calendarWithoutMaps')}</div>}
              {skill.id === 'tencent-meeting' && !meetingConfigured && <button className="skill-install-link" type="button" onClick={() => window.open('https://meeting.tencent.com/ai-skill', '_blank', 'noopener,noreferrer')}>{t('connectTencentMeeting')}</button>}
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={enabled}
              aria-label={t('toggleSkill', { action: enabled ? t('disableAction') : t('enableAction'), name: t(skill.nameKey) })}
              className={`skill-toggle ${enabled ? 'is-on' : ''}`}
              disabled={skill.locked || savingId === skill.id}
              onClick={() => void save(skill.id, !enabled)}
            ><span /></button>
          </article>;
        })}
        {!SKILLS_CATALOG.length && !loading && <div className="conversation-list-empty">{t('noSkills')}</div>}
      </div>
      <div className="skills-marketplace-footer">
        <span>{t('disabledSkillHint')}</span>
        <Button variant="outline" loading={loading} onClick={() => void refresh()}>{t('refreshStatus')}</Button>
      </div>
    </Dialog>
  </>;
}
