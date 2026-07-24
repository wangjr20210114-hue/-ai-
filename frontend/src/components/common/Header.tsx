import { useEffect, useMemo, useState } from 'react';
import { Button } from 'tdesign-react';
import { ChevronLeftIcon, ChevronRightIcon, MenuIcon, ModeDarkIcon, ModeLightIcon, NotificationIcon } from 'tdesign-icons-react';
import { useAppDispatch, useAppState } from '../../store/appState';
import StatusIndicator from './StatusIndicator';
import { activeProactiveNotifications, proactiveReminderLines } from '../profile/proactiveNotifications';
import { useLanguage } from '../../i18n';

const THEME_KEY = 'travel-theme';

/** 顶部导航栏。 */
export default function Header({
  onToggleSidebar,
  rightPanelOpen = true,
  onToggleRightPanel,
}: {
  onToggleSidebar?: () => void;
  rightPanelOpen?: boolean;
  onToggleRightPanel?: () => void;
}) {
  const { theme, connected, proactive } = useAppState();
  const { t } = useLanguage();
  const dispatch = useAppDispatch();
  const notifications = useMemo(
    () => activeProactiveNotifications(proactive?.notifications || []),
    [proactive],
  );
  const reminderLines = useMemo(
    () => proactiveReminderLines(notifications),
    [notifications],
  );
  const notificationKey = reminderLines.map((item) => item.id).join('|');
  const [reminderIndex, setReminderIndex] = useState(0);

  useEffect(() => {
    setReminderIndex(0);
  }, [notificationKey]);

  useEffect(() => {
    if (reminderLines.length < 2) return;
    const timer = window.setInterval(() => {
      setReminderIndex((value) => (value + 1) % reminderLines.length);
    }, 6000);
    return () => window.clearInterval(timer);
  }, [reminderLines.length]);

  const toggleTheme = () => {
    const next = theme === 'dark' ? 'light' : 'dark';
    const applyTheme = () => {
      document.documentElement.setAttribute('theme-mode', next);
      dispatch({ type: 'SET_THEME', payload: next });
      try {
        localStorage.setItem(THEME_KEY, next);
      } catch {
        // Theme persistence is optional.
      }
    };
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const startViewTransition = (
      document as Document & {
        startViewTransition?: (update: () => void) => { finished: Promise<void> };
      }
    ).startViewTransition;

    if (!startViewTransition || reducedMotion) {
      applyTheme();
      return;
    }

    document.documentElement.classList.add('theme-transitioning');
    const transition = startViewTransition.call(document, applyTheme);
    void transition.finished.finally(() => {
      document.documentElement.classList.remove('theme-transitioning');
    });
  };

  return (
    <header className="app-header">
      <div className="header-brand-group">
        {onToggleSidebar && (
          <Button
            className="sidebar-toggle"
            shape="circle"
            variant="text"
            size="medium"
            disabled={!connected}
            onClick={onToggleSidebar}
            aria-label={t('openConversations')}
            icon={<MenuIcon />}
          />
        )}
        <img className="header-brand-avatar" src="/floris-avatar.png" alt="" aria-hidden="true" />
        <span className="brand-logo">{t('appTitle')}</span>
      </div>
      <div className="header-proactive-slot">
        {connected && (
          <button
            type="button"
            className={`header-proactive-ticker${reminderLines.length ? '' : ' is-idle'}`}
            aria-label={reminderLines.length
              ? t('viewReminder', { text: reminderLines[reminderIndex % reminderLines.length].text })
              : t('proactiveNoNew')}
            onClick={onToggleSidebar}
          >
            <NotificationIcon size="14px" aria-hidden="true" />
            <span
              key={reminderLines.length ? reminderLines[reminderIndex % reminderLines.length].id : 'idle'}
              className="header-proactive-ticker-text"
            >
              {reminderLines.length
                ? reminderLines[reminderIndex % reminderLines.length].text
                : t('proactiveNoNew')}
            </span>
          </button>
        )}
      </div>
      <div className="header-actions">
        <StatusIndicator />
        {onToggleRightPanel && (
          <Button
            className="right-panel-toggle"
            shape="circle"
            variant="text"
            size="medium"
            disabled={!connected}
            onClick={onToggleRightPanel}
            aria-label={rightPanelOpen ? t('collapsePanel') : t('expandPanel')}
            aria-pressed={rightPanelOpen}
            icon={rightPanelOpen ? <ChevronRightIcon /> : <ChevronLeftIcon />}
          />
        )}
        <Button
          className="theme-toggle"
          shape="circle"
          variant="text"
          size="medium"
          disabled={!connected}
          onClick={toggleTheme}
          aria-label={theme === 'dark' ? t('useLightTheme') : t('useDarkTheme')}
          icon={theme === 'dark' ? <ModeLightIcon /> : <ModeDarkIcon />}
        />
      </div>
    </header>
  );
}
