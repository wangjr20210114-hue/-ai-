import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { MessagePlugin } from 'tdesign-react';
import { ChevronDownIcon, ChevronUpIcon, NotificationIcon } from 'tdesign-icons-react';
import { useAppDispatch, useAppState } from '../../../store/appState';
import type { ProactiveNotification } from '../model';
import { activeProactiveNotifications } from '../model/proactiveNotifications';
import { loadProactiveDocumentContext } from '../../../services/proactiveDocument';
import { useLanguage } from '../../../i18n';
import { useSettingsController } from '../controller/useSettingsController';

function clock(timestamp?: number | null, language = 'zh-CN'): string {
  if (!timestamp) return '';
  const locale = language === 'zh-TW' ? 'zh-TW' : language === 'en' ? 'en' : 'zh-CN';
  return new Date(timestamp * 1000).toLocaleString(locale, {
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
  });
}

export default function ProactiveBriefPanel() {
  const { language, t } = useLanguage();
  const { proactive, conversationId } = useAppState();
  const { proactive: runProactive } = useSettingsController(conversationId);
  const dispatch = useAppDispatch();
  const [mutating, setMutating] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const refreshingRef = useRef(false);
  const notifications = useMemo(
    () => activeProactiveNotifications(proactive?.notifications || []),
    [proactive],
  );

  const refresh = useCallback(async () => {
    if (refreshingRef.current) return;
    refreshingRef.current = true;
    setRefreshing(true);
    try {
      const next = await runProactive('refresh');
      dispatch({ type: 'HYDRATE_PROACTIVE', payload: next });
    } catch (error) {
      console.warn('proactive reminder refresh failed', error);
    } finally {
      refreshingRef.current = false;
      setRefreshing(false);
    }
  }, [dispatch, runProactive]);

  useEffect(() => {
    let timer = 0;
    const scheduleRefresh = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => { void refresh(); }, 160);
    };
    const onVisibility = () => { if (document.visibilityState === 'visible') scheduleRefresh(); };
    window.addEventListener('focus', scheduleRefresh);
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener('focus', scheduleRefresh);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [refresh]);

  const mutate = async (key: string, operation: string, input: Record<string, unknown>) => {
    setMutating(key);
    try {
      const next = await runProactive(operation, input);
      dispatch({ type: 'HYDRATE_PROACTIVE', payload: next });
    } catch {
      MessagePlugin.error(t('reminderOperationFailed'));
    } finally {
      setMutating('');
    }
  };

  const applySuggestion = async (item: ProactiveNotification) => {
    setMutating(`read:${item.id}`);
    try {
      const documentContext = await loadProactiveDocumentContext(item);
      dispatch({ type: 'SET_DOCUMENT_CONTEXT', payload: documentContext });
      dispatch({ type: 'SET_DRAFT', payload: item.action_prompt });
      const next = await runProactive('mark_read', { notification_id: item.id });
      dispatch({ type: 'HYDRATE_PROACTIVE', payload: next });
    } catch {
      MessagePlugin.error(t('proactiveSuggestionFailed'));
    } finally {
      setMutating('');
    }
  };

  return (
    <section className={`sidebar-reminders ${expanded ? 'is-expanded' : 'is-collapsed'}`} data-onboarding="reminders" aria-label={t('proactiveReminders')}>
      <div className="sidebar-reminders-heading">
        <button
          type="button"
          className="sidebar-reminders-toggle"
          aria-expanded={expanded}
          aria-label={t(expanded ? 'collapseReminders' : 'expandReminders')}
          title={t(expanded ? 'collapseReminders' : 'expandReminders')}
          onClick={() => setExpanded((value) => !value)}
        >
          <NotificationIcon size="15px" />
          <span>{t('reminders')}</span>
          {notifications.length > 0 && <b>{notifications.length}</b>}
          {expanded ? <ChevronUpIcon /> : <ChevronDownIcon />}
        </button>
        <button type="button" disabled={refreshing} onClick={() => { void refresh(); }} aria-label={t('refreshReminders')} title={t('refreshReminders')}>
          {refreshing ? '…' : '↻'}
        </button>
      </div>
      {expanded && (notifications.length === 0 ? (
        <div className="sidebar-reminders-empty">{t('noReminders')}</div>
      ) : notifications.map((item) => (
        <article key={item.id} className={`sidebar-reminder priority-${item.priority}`}>
          <strong>{item.title}</strong>
          <p>{item.body}</p>
          {item.status === 'snoozed' && <small>{t('remindLaterAt', { time: clock(item.snoozed_until, language) })}</small>}
          <div>
            <button type="button" disabled={Boolean(mutating)} onClick={() => { void applySuggestion(item); }}>{t('handleSuggestion')}</button>
            <button type="button" disabled={Boolean(mutating)} onClick={() => { void mutate(`snooze:${item.id}`, 'snooze', { notification_id: item.id, until: Math.floor(Date.now() / 1000) + 3600 }); }}>{t('later')}</button>
            <button type="button" disabled={Boolean(mutating)} onClick={() => { void mutate(`dismiss:${item.id}`, 'dismiss', { notification_id: item.id }); }}>{t('ignore')}</button>
          </div>
        </article>
      )))}
    </section>
  );
}
