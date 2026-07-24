import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { MessagePlugin } from 'tdesign-react';
import { NotificationIcon } from 'tdesign-icons-react';
import { useAppDispatch, useAppState } from '../../store/appState';
import { proactiveOperation } from '../../services/api';
import type { ProactiveNotification } from '../../types';
import { activeProactiveNotifications } from './proactiveNotifications';
import { loadProactiveDocumentContext } from '../../services/proactiveDocument';
import { useLanguage } from '../../i18n';

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
  const dispatch = useAppDispatch();
  const [mutating, setMutating] = useState('');
  const [refreshing, setRefreshing] = useState(false);
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
      const next = await proactiveOperation(conversationId, 'refresh');
      dispatch({ type: 'HYDRATE_PROACTIVE', payload: next });
    } catch (error) {
      console.warn('proactive reminder refresh failed', error);
    } finally {
      refreshingRef.current = false;
      setRefreshing(false);
    }
  }, [conversationId, dispatch]);

  useEffect(() => {
    let timer = 0;
    const scheduleRefresh = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => { void refresh(); }, 160);
    };
    const onVisibility = () => { if (document.visibilityState === 'visible') scheduleRefresh(); };
    scheduleRefresh();
    window.addEventListener('yuanbao:calendar-changed', scheduleRefresh);
    window.addEventListener('yuanbao:workspace-changed', scheduleRefresh);
    window.addEventListener('focus', scheduleRefresh);
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener('yuanbao:calendar-changed', scheduleRefresh);
      window.removeEventListener('yuanbao:workspace-changed', scheduleRefresh);
      window.removeEventListener('focus', scheduleRefresh);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [refresh]);

  const mutate = async (key: string, operation: string, input: Record<string, unknown>) => {
    setMutating(key);
    try {
      const next = await proactiveOperation(conversationId, operation, input);
      dispatch({ type: 'HYDRATE_PROACTIVE', payload: next });
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : t('reminderOperationFailed'));
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
      const next = await proactiveOperation(conversationId, 'mark_read', { notification_id: item.id });
      dispatch({ type: 'HYDRATE_PROACTIVE', payload: next });
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : t('proactiveSuggestionFailed'));
    } finally {
      setMutating('');
    }
  };

  return (
    <section className="sidebar-reminders" aria-label={t('proactiveReminders')}>
      <div className="sidebar-reminders-heading">
        <span><NotificationIcon size="15px" /> {t('reminders')}</span>
        {notifications.length > 0 && <b>{notifications.length}</b>}
        <button type="button" disabled={refreshing} onClick={() => { void refresh(); }} aria-label={t('refreshReminders')}>
          {refreshing ? '…' : '↻'}
        </button>
      </div>
      {notifications.length === 0 ? (
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
      ))}
    </section>
  );
}
