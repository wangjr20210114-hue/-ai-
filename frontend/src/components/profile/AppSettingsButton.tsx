import { useCallback, useEffect, useState } from 'react';
import { Button, Dialog, MessagePlugin } from 'tdesign-react';
import { AddIcon, DeleteIcon, RefreshIcon, SettingIcon } from 'tdesign-icons-react';
import { useAppDispatch, useAppState } from '../../store/appState';
import {
  DataResetError,
  getProviderUsage,
  intelligenceOperation,
  proactiveOperation,
  resetApplicationData,
} from '../../services/api';
import { getReadingSettings, updateReadingSettings } from '../../services/paperApi';
import { clearLocalApplicationData } from '../../services/conversation';
import { languageName, useLanguage, type Language } from '../../i18n';
import type { MakersIntelligenceState, ProviderUsageSummary } from '../../types';

const DEFAULT_SEARCH_PREFERENCES = {
  result_limit: 8,
  image_limit: 2,
  parallel_image_search: true,
};

const DEFAULT_MAP_PREFERENCES: NonNullable<MakersIntelligenceState['map_preferences']> = {
  service_mode: 'balanced',
  place_result_limit: 6,
  route_stop_limit: 8,
  search_timeout_seconds: 30,
  preferred_route_mode: 'driving',
  route_strategy: 'time_then_cost',
  near_time_tolerance_minutes: 10,
  semantic_colocation_radius_meters: 2000,
  learn_route_preferences: true,
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
  const [mapPreferences, setMapPreferences] = useState(DEFAULT_MAP_PREFERENCES);
  const [skillPreferences, setSkillPreferences] = useState<Record<string, boolean>>({});
  const [mottoDrafts, setMottoDrafts] = useState<string[]>([]);
  const [resetVisible, setResetVisible] = useState(false);
  const [resetPassword, setResetPassword] = useState('');
  const [resetError, setResetError] = useState('');
  const [providerUsage, setProviderUsage] = useState<ProviderUsageSummary | null>(null);
  const [providerUsageLoading, setProviderUsageLoading] = useState(false);
  const [providerUsageError, setProviderUsageError] = useState(false);

  useEffect(() => {
    if (!visible) return;
    let disposed = false;
    setLoading(true);
    void (async () => {
      const tasks = [
        intelligenceOperation(conversationId).then((state) => {
          if (disposed) return;
          setSearchPreferences(state.search_preferences || DEFAULT_SEARCH_PREFERENCES);
          setMapPreferences(state.map_preferences || DEFAULT_MAP_PREFERENCES);
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

  const loadProviderUsage = useCallback(async () => {
    setProviderUsageLoading(true);
    setProviderUsageError(false);
    try {
      setProviderUsage(await getProviderUsage(conversationId));
    } catch {
      setProviderUsageError(true);
    } finally {
      setProviderUsageLoading(false);
    }
  }, [conversationId]);

  useEffect(() => {
    if (!visible) return;
    void loadProviderUsage();
  }, [loadProviderUsage, visible]);

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
    } catch {
      MessagePlugin.error(t('proactiveSettingsSaveFailed'));
    } finally { setBusy(''); }
  };

  const saveReading = async (value: boolean) => {
    setAutomatic(value);
    setBusy('reading');
    try {
      await updateReadingSettings(value);
      MessagePlugin.success(value ? t('readingAutoEnabled') : t('readingManualEnabled'));
    } catch {
      MessagePlugin.error(t('readingSettingsSaveFailed'));
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
    } catch {
      MessagePlugin.error(t('searchSettingsSaveFailed'));
    } finally { setBusy(''); }
  };

  const saveMap = async (changes: Partial<NonNullable<MakersIntelligenceState['map_preferences']>>) => {
    const nextPreferences = { ...mapPreferences, ...changes };
    setMapPreferences(nextPreferences);
    setBusy('maps');
    try {
      const next = await intelligenceOperation(conversationId, 'update_map_preferences', {
        preferences: nextPreferences,
      });
      setMapPreferences(next.map_preferences || nextPreferences);
      MessagePlugin.success(t('mapSettingsSaved'));
    } catch {
      MessagePlugin.error(t('mapSettingsSaveFailed'));
    } finally { setBusy(''); }
  };

  const preferences = proactive?.preferences;
  const skillEnabled = (id: string) => skillPreferences[id] !== false;
  const metered = (period: 'daily' | 'monthly', metric: string) => Object.entries(
    providerUsage?.metering?.[period] || {},
  ).reduce((total, [key, value]) => total + (key.endsWith(`.${metric}`) ? Number(value) || 0 : 0), 0);
  const openSettings = () => {
    setLoading(true);
    setVisible(true);
  };
  const saveMottos = () => void setPreferences({
    fallback_mottos: mottoDrafts
      .map((item) => item.replace(/\s+/g, ' ').trim())
      .filter(Boolean)
      .slice(0, 5),
  });
  const clearAllData = async () => {
    if (!resetPassword) {
      setResetError(t('dataClearPasswordRequired'));
      return;
    }
    setBusy('reset');
    setResetError('');
    try {
      await resetApplicationData(conversationId, resetPassword);
      setResetVisible(false);
      setVisible(false);
      MessagePlugin.success(t('dataClearSucceeded'));
      window.setTimeout(() => {
        clearLocalApplicationData();
        window.location.reload();
      }, 500);
    } catch (error) {
      const key = error instanceof DataResetError && error.code === 'INVALID_PASSWORD'
        ? 'dataClearPasswordIncorrect'
        : error instanceof DataResetError && error.code === 'RESET_NOT_CONFIGURED'
          ? 'dataClearUnavailable'
          : 'dataClearFailed';
      setResetError(t(key));
      MessagePlugin.error(t(key));
    } finally {
      setBusy('');
    }
  };
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

        <section className="app-settings-section provider-usage-section">
          <div className="provider-usage-heading">
            <div>
              <h3>{t('providerUsage')}</h3>
              <p>{t('providerUsageHint')}</p>
            </div>
            <Button
              shape="circle"
              variant="text"
              size="small"
              loading={providerUsageLoading}
              icon={<RefreshIcon />}
              aria-label={t('providerUsageRefresh')}
              title={t('providerUsageRefresh')}
              onClick={() => void loadProviderUsage()}
            />
          </div>
          {providerUsage && <div className="provider-usage-grid">
            <article>
              <span>{t('providerUsageToday')}</span>
              <strong>{providerUsage.usage.daily_tokens.toLocaleString(language)}</strong>
            </article>
            <article>
              <span>{t('providerUsageMonth')}</span>
              <strong>{providerUsage.usage.monthly_tokens.toLocaleString(language)}</strong>
            </article>
            {([
              ['vision_tokens', 'visionTokenUsage'],
              ['images', 'imageGenerationUsage'],
            ] as const).map(([metric, label]) => (
              <article key={metric}>
                <span>{t(label)}</span>
                <strong>{metered('monthly', metric).toLocaleString(language)}</strong>
                <small>{t('providerUsageTodayValue', { value: metered('daily', metric).toLocaleString(language) })}</small>
              </article>
            ))}
            <article>
              <span>{t('wsaUsage')}</span>
              <strong>{Number(providerUsage.metering.monthly['wsa.requests'] || 0).toLocaleString(language)}</strong>
              <small>{t('providerUsageTodayValue', { value: Number(providerUsage.metering.daily['wsa.requests'] || 0).toLocaleString(language) })}</small>
            </article>
            <article>
              <span>{t('mapUsage')}</span>
              <strong>{Number(providerUsage.metering.monthly['tencent_maps.requests'] || 0).toLocaleString(language)}</strong>
              <small>{t('providerUsageTodayValue', { value: Number(providerUsage.metering.daily['tencent_maps.requests'] || 0).toLocaleString(language) })}</small>
            </article>
            {providerUsage.providers.flatMap((provider) => provider.balances.map((balance) => (
              <article key={`${provider.id}-${balance.currency}`}>
                <span>{t('deepseekBalance')}</span>
                <strong>{new Intl.NumberFormat(language, {
                  style: 'currency',
                  currency: balance.currency,
                }).format(Number(balance.total_balance))}</strong>
                <small>{provider.is_available ? t('balanceAvailable') : t('balanceUnavailable')}</small>
              </article>
            )))}
          </div>}
          {providerUsage && <small className="provider-usage-updated">{t('providerUsageUpdated', {
            time: new Date(providerUsage.refreshed_at * 1000).toLocaleString(language),
          })}</small>}
          {providerUsageError && <p className="provider-usage-error" role="status">{t('providerUsageLoadFailed')}</p>}
          <p className="provider-usage-limit-hint">{t('providerUsageLimitedHint')}</p>
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

        {skillEnabled('maps') && <section className="app-settings-section">
          <h3>{t('mapExperience')}</h3>
          <p>{t('mapExperienceHint')}</p>
          <div className="app-settings-grid">
            <label><span>{t('mapServiceMode')}</span><select value={mapPreferences.service_mode} disabled={busy === 'maps'} onChange={(event) => {
              const service_mode = event.target.value as NonNullable<MakersIntelligenceState['map_preferences']>['service_mode'];
              const defaults = service_mode === 'fast'
                ? { place_result_limit: 4, route_stop_limit: 4, search_timeout_seconds: 20 }
                : service_mode === 'complete'
                  ? { place_result_limit: 10, route_stop_limit: 12, search_timeout_seconds: 55 }
                  : { place_result_limit: 6, route_stop_limit: 8, search_timeout_seconds: 30 };
              void saveMap({ service_mode, ...defaults });
            }}>
              <option value="fast">{t('mapModeFast')}</option>
              <option value="balanced">{t('mapModeBalanced')}</option>
              <option value="complete">{t('mapModeComplete')}</option>
            </select></label>
            <label><span>{t('mapPlaceResultCount')}</span><select value={mapPreferences.place_result_limit} disabled={busy === 'maps'} onChange={(event) => void saveMap({ place_result_limit: Number(event.target.value) })}>
              {[3, 4, 6, 8, 10, 12].map((value) => <option key={value} value={value}>{t('numericValue', { value })}</option>)}
            </select></label>
            <label><span>{t('mapRouteStopCount')}</span><select value={mapPreferences.route_stop_limit} disabled={busy === 'maps'} onChange={(event) => void saveMap({ route_stop_limit: Number(event.target.value) })}>
              {[4, 6, 8, 10, 12].map((value) => <option key={value} value={value}>{t('numericValue', { value })}</option>)}
            </select></label>
            <label><span>{t('mapSearchTimeout')}</span><select value={mapPreferences.search_timeout_seconds} disabled={busy === 'maps'} onChange={(event) => void saveMap({ search_timeout_seconds: Number(event.target.value) })}>
              <option value={15}>{t('secondsValue', { value: 15 })}</option>
              <option value={20}>{t('secondsValue', { value: 20 })}</option>
              <option value={30}>{t('secondsValue', { value: 30 })}</option>
              <option value={45}>{t('secondsValue', { value: 45 })}</option>
              <option value={55}>{t('secondsValue', { value: 55 })}</option>
            </select></label>
            <label><span>{t('preferredRouteMode')}</span><select value={mapPreferences.preferred_route_mode} disabled={busy === 'maps'} onChange={(event) => void saveMap({ preferred_route_mode: event.target.value as NonNullable<MakersIntelligenceState['map_preferences']>['preferred_route_mode'] })}>
              <option value="driving">{t('routeModeDriving')}</option>
              <option value="transit">{t('routeModeTransit')}</option>
              <option value="walking">{t('routeModeWalking')}</option>
              <option value="bicycling">{t('routeModeBicycling')}</option>
            </select></label>
            <label><span>{t('routeStrategy')}</span><select value={mapPreferences.route_strategy} disabled={busy === 'maps'} onChange={(event) => void saveMap({ route_strategy: event.target.value as NonNullable<MakersIntelligenceState['map_preferences']>['route_strategy'] })}>
              <option value="time_then_cost">{t('routeStrategyTimeThenCost')}</option>
              <option value="least_time">{t('routeStrategyLeastTime')}</option>
              <option value="least_cost">{t('routeStrategyLeastCost')}</option>
            </select></label>
            <label><span>{t('nearTimeTolerance')}</span><select value={mapPreferences.near_time_tolerance_minutes} disabled={busy === 'maps'} onChange={(event) => void saveMap({ near_time_tolerance_minutes: Number(event.target.value) })}>
              {[0, 5, 10, 15, 20, 30].map((value) => <option key={value} value={value}>{t('routeToleranceMinutes', { value })}</option>)}
            </select></label>
            <label><span>{t('semanticColocationRadius')}</span><select value={mapPreferences.semantic_colocation_radius_meters} disabled={busy === 'maps'} onChange={(event) => void saveMap({ semantic_colocation_radius_meters: Number(event.target.value) })}>
              {[100, 500, 1000, 2000, 5000].map((value) => <option key={value} value={value}>{t('metersValue', { value })}</option>)}
            </select></label>
            <label><span>{t('learnRoutePreferences')}</span><input type="checkbox" checked={mapPreferences.learn_route_preferences !== false} disabled={busy === 'maps'} onChange={(event) => void saveMap({ learn_route_preferences: event.target.checked })} /></label>
          </div>
        </section>}

        {skillEnabled('proactive-agent') && <section className="app-settings-section">
          <h3>{t('proactive')}</h3>
          <p>{t('proactiveHint')}</p>
          {preferences && <div className="app-settings-grid">
            <label><span>{t('proactiveEnabled')}</span><input type="checkbox" checked={preferences.enabled !== false} disabled={busy === 'proactive'} onChange={(event) => void setPreferences({ enabled: event.target.checked })} /></label>
            <label><span>{t('lookaheadRange')}</span><select value={preferences.lookahead_hours} disabled={busy === 'proactive'} onChange={(event) => void setPreferences({ lookahead_hours: Number(event.target.value) })}><option value={12}>{t('next12Hours')}</option><option value={24}>{t('next24Hours')}</option><option value={48}>{t('next48Hours')}</option><option value={72}>{t('next3Days')}</option></select></label>
            <label><span>{t('providerScheduleCount')}</span><select value={preferences.provider_schedule_limit} disabled={busy === 'proactive'} onChange={(event) => void setPreferences({ provider_schedule_limit: Number(event.target.value) })}>{[4, 6, 8, 12].map((value) => <option key={value} value={value}>{t('numericValue', { value })}</option>)}</select></label>
            <label><span>{t('routeGapHours')}</span><select value={preferences.route_gap_hours} disabled={busy === 'proactive'} onChange={(event) => void setPreferences({ route_gap_hours: Number(event.target.value) })}>{[1, 2, 3, 4, 6, 8].map((value) => <option key={value} value={value}>{t('numericValue', { value })}</option>)}</select></label>
            <label><span>{t('travelBufferMinutes')}</span><select value={preferences.travel_buffer_minutes} disabled={busy === 'proactive'} onChange={(event) => void setPreferences({ travel_buffer_minutes: Number(event.target.value) })}>{[0, 10, 15, 30, 45, 60].map((value) => <option key={value} value={value}>{t('numericValue', { value })}</option>)}</select></label>
            <label><span>{t('quietHours')}</span><input type="checkbox" checked={preferences.quiet_hours.enabled} disabled={busy === 'proactive'} onChange={(event) => void setPreferences({ quiet_hours: { ...preferences.quiet_hours, enabled: event.target.checked } })} /></label>
            <Button size="small" variant="outline" loading={busy === 'scan'} onClick={() => {
              setBusy('scan');
              void proactiveOperation(conversationId, 'refresh').then((next) => {
                dispatch({ type: 'HYDRATE_PROACTIVE', payload: next });
                MessagePlugin.success(t('proactiveChecked'));
              }).catch(() => MessagePlugin.error(t('checkFailed'))).finally(() => setBusy(''));
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

        <section className="app-settings-section app-settings-danger-section">
          <div>
            <h3>{t('dataManagement')}</h3>
            <p>{t('dataClearHint')}</p>
          </div>
          <Button
            theme="danger"
            variant="outline"
            icon={<DeleteIcon />}
            onClick={() => {
              setResetPassword('');
              setResetError('');
              setResetVisible(true);
            }}
          >{t('clearDatabase')}</Button>
        </section>
      </div>
    </Dialog>
    <Dialog
      visible={resetVisible}
      header={t('clearDatabase')}
      width={480}
      placement="center"
      dialogClassName="secondary-dialog data-clear-dialog"
      footer={false}
      onClose={() => !busy && setResetVisible(false)}
      onCancel={() => !busy && setResetVisible(false)}
    >
      <div className="data-clear-content">
        <div className="data-clear-warning">
          <DeleteIcon />
          <div>
            <strong>{t('dataClearWarningTitle')}</strong>
            <p>{t('dataClearWarningBody')}</p>
          </div>
        </div>
        <label className="data-clear-password">
          <span>{t('dataClearPassword')}</span>
          <input
            type="password"
            autoComplete="current-password"
            value={resetPassword}
            disabled={busy === 'reset'}
            placeholder={t('dataClearPasswordPlaceholder')}
            onChange={(event) => {
              setResetPassword(event.target.value);
              setResetError('');
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && busy !== 'reset') void clearAllData();
            }}
          />
          {resetError && <small role="alert">{resetError}</small>}
        </label>
        <div className="data-clear-actions">
          <Button variant="outline" disabled={busy === 'reset'} onClick={() => setResetVisible(false)}>{t('cancel')}</Button>
          <Button theme="danger" loading={busy === 'reset'} onClick={() => void clearAllData()}>{t('confirmClearDatabase')}</Button>
        </div>
      </div>
    </Dialog>
  </>;
}
