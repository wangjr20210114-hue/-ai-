import { useEffect, useState } from 'react';
import { Button, Dialog, MessagePlugin } from 'tdesign-react';
import { AddIcon, DeleteIcon, SettingIcon } from 'tdesign-icons-react';
import { useAppDispatch, useAppState } from '../../store/appState';
import { intelligenceOperation, proactiveOperation } from '../../services/api';
import { getReadingSettings, updateReadingSettings } from '../../services/paperApi';
import { languageName, useLanguage, type Language } from '../../i18n';
import type { MakersIntelligenceState } from '../../types';

const DEFAULT_SEARCH_PREFERENCES = {
  result_limit: 8,
  image_limit: 2,
  parallel_image_search: true,
};

export default function AppSettingsButton() {
  const { conversationId, proactive } = useAppState();
  const { language, setLanguage, t } = useLanguage();
  const dispatch = useAppDispatch();
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState('');
  const [automatic, setAutomatic] = useState(true);
  const [loading, setLoading] = useState(false);
  const [searchPreferences, setSearchPreferences] = useState(DEFAULT_SEARCH_PREFERENCES);
  const [skillPreferences, setSkillPreferences] = useState<Record<string, boolean>>({});
  const [mottoDrafts, setMottoDrafts] = useState<string[]>([]);

  useEffect(() => {
    if (!visible) return;
    let disposed = false;
    setLoading(true);
    void (async () => {
      const tasks = [
        intelligenceOperation(conversationId).then((state) => {
          if (disposed) return;
          setSearchPreferences(state.search_preferences || DEFAULT_SEARCH_PREFERENCES);
          setSkillPreferences(state.skill_preferences || {});
        }),
        getReadingSettings().then((settings) => {
          if (!disposed) setAutomatic(settings.auto_organize);
        }),
      ];
      const results = await Promise.allSettled(tasks);
      results.forEach((result) => {
        if (result.status === 'rejected') console.warn('settings refresh failed', result.reason);
      });
      if (!disposed) {
        setLoading(false);
      }
    })();
    return () => {
      disposed = true;
    };
  }, [conversationId, visible]);

  useEffect(() => {
    if (!visible || proactive) return;
    let disposed = false;
    void proactiveOperation(conversationId, 'get').then((next) => {
      if (!disposed) dispatch({ type: 'HYDRATE_PROACTIVE', payload: next });
    }).catch((error) => console.warn('proactive settings read failed', error));
    return () => {
      disposed = true;
    };
  }, [conversationId, dispatch, proactive, visible]);

  useEffect(() => {
    if (visible && proactive?.preferences) {
      setMottoDrafts([...(proactive.preferences.fallback_mottos || [])]);
    }
  }, [proactive?.preferences, visible]);

  useEffect(() => {
    const changed = (event: Event) => {
      const detail = (event as CustomEvent<Record<string, boolean>>).detail;
      if (detail) setSkillPreferences(detail);
    };
    window.addEventListener('yuanbao:skills-changed', changed);
    return () => window.removeEventListener('yuanbao:skills-changed', changed);
  }, []);

  const setPreferences = async (changes: Record<string, unknown>) => {
    setBusy('proactive');
    try {
      const next = await proactiveOperation(conversationId, 'update_preferences', {
        preferences: { ...(proactive?.preferences || {}), ...changes },
      });
      dispatch({ type: 'HYDRATE_PROACTIVE', payload: next });
      MessagePlugin.success(t('proactiveSettingsSaved'));
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : t('proactiveSettingsSaveFailed'));
    } finally { setBusy(''); }
  };

  const saveReading = async (value: boolean) => {
    setAutomatic(value);
    setBusy('reading');
    try {
      await updateReadingSettings(value);
      MessagePlugin.success(value ? t('readingAutoEnabled') : t('readingManualEnabled'));
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : t('readingSettingsSaveFailed'));
    } finally { setBusy(''); }
  };

  const saveSearch = async (changes: Partial<NonNullable<MakersIntelligenceState['search_preferences']>>) => {
    const nextPreferences = { ...searchPreferences, ...changes };
    setSearchPreferences(nextPreferences);
    setBusy('search');
    try {
      const next = await intelligenceOperation(conversationId, 'update_search_preferences', {
        preferences: nextPreferences,
      });
      setSearchPreferences(next.search_preferences || nextPreferences);
      MessagePlugin.success(t('searchSettingsSaved'));
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : t('searchSettingsSaveFailed'));
    } finally { setBusy(''); }
  };

  const preferences = proactive?.preferences;
  const skillEnabled = (id: string) => skillPreferences[id] !== false;
  const openSettings = () => {
    setVisible(true);
  };
  const saveMottos = () => void setPreferences({
    fallback_mottos: mottoDrafts
      .map((item) => item.replace(/\s+/g, ' ').trim())
      .filter(Boolean)
      .slice(0, 5),
  });
  return <>
    <Button className="sidebar-settings-button" block variant="text" icon={<SettingIcon />} onClick={openSettings}>{t('settings')}</Button>
    <Dialog
      visible={visible}
      header={t('settingsTitle')}
      width={720}
      placement="center"
      dialogClassName="secondary-dialog app-settings-modal"
      footer={false}
      onClose={() => setVisible(false)}
      onCancel={() => setVisible(false)}
    >
      <div className={`app-settings-dialog ${loading ? 'is-loading' : ''}`} aria-busy={loading}>
        <section className="app-settings-section">
          <h3>{t('language')}</h3>
          <select className="settings-language-select" value={language} onChange={(event) => setLanguage(event.target.value as Language)}>
            {(['zh-CN', 'zh-TW', 'en', 'cat-cute', 'cat-cold'] as Language[]).map((item) => <option key={item} value={item}>{languageName(item)}</option>)}
          </select>
          <p className="settings-language-hint">{t('languageHint')}</p>
        </section>

        {skillEnabled('web-search') && <section className="app-settings-section">
          <h3>{t('searchExperience')}</h3>
          <p>{t('searchExperienceHint')}</p>
          <div className="app-settings-grid">
            <label><span>{t('searchResultCount')}</span><select value={searchPreferences.result_limit} disabled={busy === 'search'} onChange={(event) => void saveSearch({ result_limit: Number(event.target.value) })}>
              <option value={4}>{t('searchCompact')}</option>
              <option value={8}>{t('searchBalanced')}</option>
              <option value={12}>{t('searchRich')}</option>
              <option value={18}>{t('searchMax')}</option>
            </select></label>
            <label><span>{t('searchImageCount')}</span><select value={searchPreferences.image_limit} disabled={busy === 'search'} onChange={(event) => void saveSearch({ image_limit: Number(event.target.value) })}>
              <option value={0}>{t('searchImagesOff')}</option>
              <option value={1}>{t('searchImagesOne')}</option>
              <option value={2}>{t('searchImagesTwo')}</option>
              <option value={4}>{t('searchImagesFour')}</option>
            </select></label>
            <label><span>{t('parallelImageSearch')}</span><input type="checkbox" checked={searchPreferences.parallel_image_search} disabled={busy === 'search'} onChange={(event) => void saveSearch({ parallel_image_search: event.target.checked })} /></label>
          </div>
        </section>}

        {skillEnabled('proactive-agent') && <section className="app-settings-section">
          <h3>{t('proactive')}</h3>
          <p>{t('proactiveHint')}</p>
          {preferences && <div className="app-settings-grid">
            <label><span>{t('proactiveEnabled')}</span><input type="checkbox" checked={preferences.enabled !== false} disabled={busy === 'proactive'} onChange={(event) => void setPreferences({ enabled: event.target.checked })} /></label>
            <label><span>{t('lookaheadRange')}</span><select value={preferences.lookahead_hours} disabled={busy === 'proactive'} onChange={(event) => void setPreferences({ lookahead_hours: Number(event.target.value) })}><option value={12}>{t('next12Hours')}</option><option value={24}>{t('next24Hours')}</option><option value={48}>{t('next48Hours')}</option><option value={72}>{t('next3Days')}</option></select></label>
            <label><span>{t('quietHours')}</span><input type="checkbox" checked={preferences.quiet_hours.enabled} disabled={busy === 'proactive'} onChange={(event) => void setPreferences({ quiet_hours: { ...preferences.quiet_hours, enabled: event.target.checked } })} /></label>
            <Button size="small" variant="outline" loading={busy === 'scan'} onClick={() => {
              setBusy('scan');
              void proactiveOperation(conversationId, 'refresh').then((next) => {
                dispatch({ type: 'HYDRATE_PROACTIVE', payload: next });
                MessagePlugin.success(t('proactiveChecked'));
              }).catch((error) => MessagePlugin.error(error instanceof Error ? error.message : t('checkFailed'))).finally(() => setBusy(''));
            }}>{t('checkNow')}</Button>
          </div>}
          {preferences && <div className="proactive-motto-editor">
            <div className="proactive-motto-heading">
              <div>
                <strong>{t('fallbackMottos')}</strong>
                <small>{t('fallbackMottosHint')}</small>
              </div>
              <span>{t('mottoCount', { count: mottoDrafts.length })}</span>
            </div>
            <div className="proactive-motto-list">
              {mottoDrafts.map((motto, index) => (
                <div key={index} className="proactive-motto-row">
                  <input
                    value={motto}
                    maxLength={80}
                    disabled={busy === 'proactive'}
                    aria-label={t('mottoNumber', { number: index + 1 })}
                    placeholder={t('mottoPlaceholder')}
                    onChange={(event) => setMottoDrafts((items) => items.map((item, itemIndex) => (
                      itemIndex === index ? event.target.value : item
                    )))}
                  />
                  <Button
                    shape="circle"
                    variant="text"
                    size="small"
                    disabled={busy === 'proactive'}
                    aria-label={t('removeMottoNumber', { number: index + 1 })}
                    title={t('remove')}
                    icon={<DeleteIcon />}
                    onClick={() => setMottoDrafts((items) => items.filter((_, itemIndex) => itemIndex !== index))}
                  />
                </div>
              ))}
            </div>
            <div className="proactive-motto-actions">
              <Button
                size="small"
                variant="outline"
                disabled={busy === 'proactive' || mottoDrafts.length >= 5}
                icon={<AddIcon />}
                onClick={() => setMottoDrafts((items) => [...items, ''])}
              >{t('addMotto')}</Button>
              <Button
                size="small"
                theme="primary"
                loading={busy === 'proactive'}
                onClick={saveMottos}
              >{t('saveMottos')}</Button>
            </div>
          </div>}
          <details className="proactive-settings-runs">
            <summary>{t('runDiagnostics')}</summary>
            <p>{t('lastChecked', { time: proactive?.last_tick?.finished_at ? new Date(proactive.last_tick.finished_at * 1000).toLocaleString(language) : t('neverChecked') })}</p>
            <div>
              {(proactive?.runs || []).slice(0, 12).map((run) => <div key={run.id}><span>{run.intent}</span><b>{run.status}</b><small>{run.reason || run.trigger_origin}</small></div>)}
              {!proactive?.runs?.length && <span>{t('noRunHistory')}</span>}
            </div>
          </details>
        </section>}

        {skillEnabled('paper-reading') && <section className="app-settings-section">
          <h3>{t('readingLibrary')}</h3>
          <label className="app-settings-choice"><input type="radio" checked={automatic} disabled={busy === 'reading'} onChange={() => void saveReading(true)} /><span><strong>{t('autoOrganize')}</strong><small>{t('autoFilingDescription')}</small></span></label>
          <label className="app-settings-choice"><input type="radio" checked={!automatic} disabled={busy === 'reading'} onChange={() => void saveReading(false)} /><span><strong>{t('manualOrganize')}</strong><small>{t('manualFilingDescription')}</small></span></label>
        </section>}
      </div>
    </Dialog>
  </>;
}
