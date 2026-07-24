import { useEffect, useState } from 'react';
import { Button, Dialog, MessagePlugin } from 'tdesign-react';
import { SettingIcon } from 'tdesign-icons-react';
import { useAppDispatch, useAppState } from '../../store/appState';
import { proactiveOperation } from '../../services/api';
import { getReadingLibrary, updateReadingSettings } from '../../services/paperApi';
import { languageName, useLanguage, type Language } from '../../i18n';

export default function AppSettingsButton() {
  const { conversationId, proactive } = useAppState();
  const { language, setLanguage, t } = useLanguage();
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

  const preferences = proactive?.preferences;
  return <>
    <Button className="sidebar-settings-button" block variant="text" icon={<SettingIcon />} onClick={() => setVisible(true)}>{t('settings')}</Button>
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
      <div className="app-settings-dialog">
        <section className="app-settings-section">
          <h3>{t('language')}</h3>
          <select className="settings-language-select" value={language} onChange={(event) => setLanguage(event.target.value as Language)}>
            {(['zh-CN', 'zh-TW', 'en', 'cat-cute', 'cat-cold'] as Language[]).map((item) => <option key={item} value={item}>{languageName(item)}</option>)}
          </select>
          <p className="settings-language-hint">{t('languageHint')}</p>
        </section>
        <section className="app-settings-section">
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
          <details className="proactive-settings-runs">
            <summary>{t('runDiagnostics')}</summary>
            <p>{t('lastChecked', { time: proactive?.last_tick?.finished_at ? new Date(proactive.last_tick.finished_at * 1000).toLocaleString(language) : t('neverChecked') })}</p>
            <div>
              {(proactive?.runs || []).slice(0, 12).map((run) => <div key={run.id}><span>{run.intent}</span><b>{run.status}</b><small>{run.reason || run.trigger_origin}</small></div>)}
              {!proactive?.runs?.length && <span>{t('noRunHistory')}</span>}
            </div>
          </details>
        </section>

        <section className="app-settings-section">
          <h3>{t('readingLibrary')}</h3>
          <label className="app-settings-choice"><input type="radio" checked={automatic} disabled={busy === 'reading'} onChange={() => void saveReading(true)} /><span><strong>{t('autoOrganize')}</strong><small>{t('autoFilingDescription')}</small></span></label>
          <label className="app-settings-choice"><input type="radio" checked={!automatic} disabled={busy === 'reading'} onChange={() => void saveReading(false)} /><span><strong>{t('manualOrganize')}</strong><small>{t('manualFilingDescription')}</small></span></label>
        </section>
      </div>
    </Dialog>
  </>;
}
