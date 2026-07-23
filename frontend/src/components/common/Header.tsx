import { useEffect, useMemo, useState } from 'react';
import { Button, Tooltip } from 'tdesign-react';
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
  const { language } = useLanguage();
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
    dispatch({ type: 'SET_THEME', payload: next });
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      // ignore
    }
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
            aria-label={language === 'en' ? 'Open conversations' : '打开对话历史'}
            icon={<MenuIcon />}
          />
        )}
        <img className="header-brand-avatar" src="/floris-avatar.png" alt="" aria-hidden="true" />
        <span className="brand-logo">FLORIS:一只有温度的大橘</span>
      </div>
      <div className="header-proactive-slot">
        {connected && reminderLines.length > 0 && (
          <button
            type="button"
            className="header-proactive-ticker"
            aria-label={`查看主动提醒：${reminderLines[reminderIndex % reminderLines.length].text}`}
            onClick={onToggleSidebar}
          >
            <NotificationIcon size="14px" aria-hidden="true" />
            <span key={reminderLines[reminderIndex % reminderLines.length].id} className="header-proactive-ticker-text">
              {reminderLines[reminderIndex % reminderLines.length].text}
            </span>
          </button>
        )}
      </div>
      <div className="header-actions">
        <StatusIndicator />
        {onToggleRightPanel && (
          <Tooltip content={rightPanelOpen ? (language === 'en' ? 'Collapse panel' : '收起右栏') : (language === 'en' ? 'Expand panel' : '展开右栏')}>
            <Button
              className="right-panel-toggle"
              shape="circle"
              variant="text"
              size="medium"
              disabled={!connected}
              onClick={onToggleRightPanel}
              aria-label={rightPanelOpen ? (language === 'en' ? 'Collapse panel' : '收起右栏') : (language === 'en' ? 'Expand panel' : '展开右栏')}
              aria-pressed={rightPanelOpen}
              icon={rightPanelOpen ? <ChevronRightIcon /> : <ChevronLeftIcon />}
            />
          </Tooltip>
        )}
        <Tooltip content={theme === 'dark' ? (language === 'en' ? 'Switch to light' : '切换到浅色') : (language === 'en' ? 'Switch to dark' : '切换到深色')}>
          <Button
            className="theme-toggle"
            shape="circle"
            variant="text"
            size="medium"
            disabled={!connected}
            onClick={toggleTheme}
            icon={theme === 'dark' ? <ModeLightIcon /> : <ModeDarkIcon />}
          />
        </Tooltip>
      </div>
    </header>
  );
}
