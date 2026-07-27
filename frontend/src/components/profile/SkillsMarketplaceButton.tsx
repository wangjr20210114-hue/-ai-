import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Dialog, MessagePlugin, Tag } from 'tdesign-react';
import { AppIcon } from 'tdesign-icons-react';
import { useAppState } from '../../store/appState';
import { configureSkillConnection, skillsOperation } from '../../services/api';
import { useLanguage } from '../../i18n';
import type { InstalledSkill, SkillConnectionState } from '../../types';

export default function SkillsMarketplaceButton() {
  const { conversationId } = useAppState();
  const { t, language } = useLanguage();
  const [visible, setVisible] = useState(false);
  const [preferences, setPreferences] = useState<Record<string, boolean>>({});
  const [catalog, setCatalog] = useState<InstalledSkill[]>([]);
  const [loading, setLoading] = useState(false);
  const [savingId, setSavingId] = useState('');
  const [connections, setConnections] = useState<Record<string, SkillConnectionState>>({});
  const [tokenDrafts, setTokenDrafts] = useState<Record<string, string>>({});

  const refresh = useCallback(async (): Promise<boolean> => {
    setLoading(true);
    try {
      const result = await skillsOperation(conversationId);
      setPreferences(result.preferences);
      setCatalog(result.catalog);
      setConnections(result.connections);
      return true;
    } catch {
      MessagePlugin.error(t('skillsReadFailed'));
      return false;
    } finally { setLoading(false); }
  }, [conversationId, t]);

  const openMarketplace = useCallback(async () => {
    if (catalog.length) {
      setVisible(true);
      void refresh();
      return;
    }
    if (await refresh()) setVisible(true);
  }, [catalog.length, refresh]);

  useEffect(() => {
    const open = () => { void openMarketplace(); };
    window.addEventListener('yuanbao:open-skills', open);
    return () => window.removeEventListener('yuanbao:open-skills', open);
  }, [openMarketplace]);

  const enabledCount = useMemo(
    () => catalog.filter((skill) => skill.locked || preferences[skill.id] !== false).length,
    [catalog, preferences],
  );
  const skillText = useCallback((
    values: Record<string, string> | undefined,
    fallback: string,
  ) => values?.[language] || values?.['zh-CN'] || values?.en || fallback, [language]);
  const skillName = useCallback((skillId: string) => {
    const skill = catalog.find((item) => item.id === skillId);
    return skill ? skillText(skill.name, skill.id) : skillId;
  }, [catalog, skillText]);
  const save = async (skillId: string, enabled: boolean) => {
    const skill = catalog.find((item) => item.id === skillId);
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
      setCatalog(result.catalog);
      window.dispatchEvent(new CustomEvent('yuanbao:skills-changed', { detail: result.preferences }));
      if (autoEnabled.length) {
        MessagePlugin.success(t('skillsDependenciesEnabled', { names: autoEnabled.map((id) => {
          return skillName(id);
        }).join('、') }));
      } else {
        MessagePlugin.success(t('skillStateChanged', { name: skillText(skill.name, skill.id), state: enabled ? t('enabled') : t('disabled') }));
      }
    } catch {
      MessagePlugin.error(t('skillsSaveFailed'));
    } finally { setSavingId(''); }
  };
  const saveConnection = async (skillId: string) => {
    const token = String(tokenDrafts[skillId] || '').trim();
    if (!token) return;
    setSavingId(skillId);
    try {
      const state = await configureSkillConnection(conversationId, skillId, token);
      setCatalog(state.skill_catalog || []);
      setConnections(state.skill_connections || {});
      setTokenDrafts((current) => ({ ...current, [skillId]: '' }));
      MessagePlugin.success(t('skillTokenSaved'));
    } catch {
      MessagePlugin.error(t('skillTokenSaveFailed'));
    } finally { setSavingId(''); }
  };
  const disconnect = async (skillId: string) => {
    setSavingId(skillId);
    try {
      const state = await configureSkillConnection(conversationId, skillId);
      setCatalog(state.skill_catalog || []);
      setConnections(state.skill_connections || {});
      MessagePlugin.success(t('skillDisconnected'));
    } catch {
      MessagePlugin.error(t('skillTokenSaveFailed'));
    } finally { setSavingId(''); }
  };

  return <>
    <Button
      className="sidebar-settings-button"
      block
      variant="text"
      icon={<AppIcon />}
      loading={loading && !visible}
      onClick={() => void openMarketplace()}
    >{t('skillsMarketplace')}</Button>
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
        <Tag theme="primary" variant="light">{loading ? t('loading') : t('enabledCount', { enabled: enabledCount, total: catalog.length })}</Tag>
      </div>
      <div className="skills-marketplace" aria-busy={loading}>
        {catalog.map((skill) => {
          const enabled = skill.locked || preferences[skill.id] !== false;
          const missingRecommended = (skill.recommends || []).filter((id) => preferences[id] === false);
          const missingRequired = (skill.requires || []).filter((id) => preferences[id] === false);
          const blocked = enabled && missingRequired.length > 0;
          const connected = skill.configured;
          const connection = connections[skill.id];
          const credentialInstructions = skill.credential?.instructions
            ? skillText(skill.credential.instructions, '')
            : '';
          return <article className={`skill-market-card ${enabled ? 'is-enabled' : 'is-disabled'}`} key={skill.id}>
            <div className="skill-market-icon" aria-hidden="true">{skill.icon}</div>
            <div className="skill-market-content">
              <div className="skill-market-title">
                <strong>{skillText(skill.name, skill.id)}</strong>
                {skill.locked && <Tag size="small">{t('core')}</Tag>}
                {skill.external && <Tag size="small" theme={connected ? 'success' : 'warning'}>{connected ? t('connected') : t('waitingConnection')}</Tag>}
              </div>
              <p>{skillText(skill.description, '')}</p>
              {blocked && <div className="skill-dependency-note is-blocked">{t('requiresSkills', { names: missingRequired.map((id) => {
                return skillName(id);
              }).join('、') })}</div>}
              {!blocked && enabled && missingRecommended.length > 0 && <div className="skill-dependency-note">{t('recommendsSkills', { names: missingRecommended.map((id) => {
                return skillName(id);
              }).join('、') })}</div>}
              {skill.external && skill.credential?.kind === 'token' && (
                <div
                  className={`skill-credential-region ${connected ? 'is-connected' : 'is-disconnected'}`}
                  key={`${skill.id}:${connected ? 'connected' : 'disconnected'}`}
                >
                  {!connected ? <>
                    {credentialInstructions && <div className="skill-credential-help">{credentialInstructions}</div>}
                    <div className="skill-credential-editor">
                      <input
                        type="password"
                        autoComplete="off"
                        value={tokenDrafts[skill.id] || ''}
                        disabled={savingId === skill.id}
                        placeholder={t('skillTokenPlaceholder')}
                        onChange={(event) => setTokenDrafts((current) => ({
                          ...current,
                          [skill.id]: event.target.value,
                        }))}
                      />
                      <Button size="small" theme="primary" loading={savingId === skill.id} disabled={!String(tokenDrafts[skill.id] || '').trim()} onClick={() => void saveConnection(skill.id)}>{t('saveConnection')}</Button>
                    </div>
                    <div className="skill-credential-actions">
                      {skill.connect_url && <button className="skill-install-link" type="button" onClick={() => window.open(skill.connect_url, '_blank', 'noopener,noreferrer')}>{t('getTokenOfficial')}</button>}
                      {skill.credential.help_url && <button className="skill-install-link" type="button" onClick={() => window.open(skill.credential?.help_url, '_blank', 'noopener,noreferrer')}>{t('viewOfficialGuide')}</button>}
                    </div>
                  </> : (
                    <div className="skill-credential-connected">
                      {connection?.expires_at && <span>{t('connectionExpiresAt', { time: new Date(connection.expires_at * 1000).toLocaleString() })}</span>}
                      {connection?.configured && <button className="skill-install-link is-danger" type="button" disabled={savingId === skill.id} onClick={() => void disconnect(skill.id)}>{t('disconnectSkill')}</button>}
                    </div>
                  )}
                </div>
              )}
              {skill.external && !skill.credential?.kind && !connected && skill.connect_url && <button className="skill-install-link" type="button" onClick={() => window.open(skill.connect_url, '_blank', 'noopener,noreferrer')}>{t('connectExternalSkill')}</button>}
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={enabled}
              aria-label={t('toggleSkill', { action: enabled ? t('disableAction') : t('enableAction'), name: skillText(skill.name, skill.id) })}
              title={t('toggleSkill', { action: enabled ? t('disableAction') : t('enableAction'), name: skillText(skill.name, skill.id) })}
              className={`skill-toggle ${enabled ? 'is-on' : ''}`}
              disabled={skill.locked || loading || savingId === skill.id}
              onClick={() => void save(skill.id, !enabled)}
            ><span /></button>
          </article>;
        })}
        {!catalog.length && !loading && <div className="conversation-list-empty">{t('noSkills')}</div>}
      </div>
      <div className="skills-marketplace-footer">
        <span>{t('disabledSkillHint')}</span>
        <Button variant="outline" loading={loading} onClick={() => void refresh()}>{t('refreshStatus')}</Button>
      </div>
    </Dialog>
  </>;
}
