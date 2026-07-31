import { useEffect, useMemo, useState } from 'react';
import { Button } from 'tdesign-react';
import { ChevronLeftIcon, ChevronRightIcon, LogoGithubIcon, MenuIcon, ModeDarkIcon, ModeLightIcon, NotificationIcon } from 'tdesign-icons-react';
import { useAppDispatch, useAppState } from '../../store/appState';
import StatusIndicator from './StatusIndicator';
import { activeProactiveNotifications, proactiveFallbackLines, proactiveHeaderLines, proactiveReminderLines } from '../profile/proactiveNotifications';
import { useLanguage } from '../../i18n';
import { FEATURE_DOCUMENT_URL } from '../../constants';
import {
  currentAuthSession,
  ensureAuthSession,
  startWechatLogin,
  type AuthSession,
} from '../../services/auth';

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
  const fallbackLines = useMemo(
    () => proactiveFallbackLines(proactive?.preferences.fallback_mottos || []),
    [proactive?.preferences.fallback_mottos],
  );
  const displayLines = useMemo(
    () => proactiveHeaderLines(reminderLines, fallbackLines, 10),
    [fallbackLines, reminderLines],
  );
  const notificationKey = displayLines.map((item) => item.id).join('|');
  const [reminderIndex, setReminderIndex] = useState(0);
  const [authSession, setAuthSession] = useState<AuthSession | null>(
    currentAuthSession(),
  );
  const activeLine = displayLines[reminderIndex % Math.max(1, displayLines.length)];

  useEffect(() => {
    setReminderIndex(0);
  }, [notificationKey]);

  useEffect(() => {
    if (displayLines.length < 2) return;
    const timer = window.setInterval(() => {
      setReminderIndex((value) => (value + 1) % displayLines.length);
    }, 6000);
    return () => window.clearInterval(timer);
  }, [displayLines.length]);

  useEffect(() => {
    if (!connected) return undefined;
    void ensureAuthSession().then(setAuthSession).catch(() => {});
    const changed = (event: Event) => {
      setAuthSession((event as CustomEvent<AuthSession>).detail);
    };
    window.addEventListener('floris:auth-changed', changed);
    return () => window.removeEventListener('floris:auth-changed', changed);
  }, [connected]);

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
            title={t('openConversations')}
            icon={<MenuIcon />}
          />
        )}
        <img className="header-brand-avatar" src="/floris-avatar.png" alt="" aria-hidden="true" />
        <span className="brand-logo">{t('appTitle')}</span>
      </div>
      <div className="header-proactive-slot">
        {connected && proactive?.preferences.enabled !== false && (
          <button
            type="button"
            data-onboarding="header-reminder"
            className={`header-proactive-ticker${activeLine?.notificationId ? '' : ' is-fallback'}`}
            aria-label={displayLines.length
              ? (activeLine?.notificationId
                ? t('viewReminder', { text: activeLine.text })
                : activeLine.text)
              : t('proactiveNoNew')}
            onClick={activeLine?.notificationId ? onToggleSidebar : undefined}
          >
            <NotificationIcon size="14px" aria-hidden="true" />
            <span
              key={displayLines.length ? displayLines[reminderIndex % displayLines.length].id : 'idle'}
              className="header-proactive-ticker-text"
            >
              {displayLines.length
                ? activeLine.text
                : t('proactiveNoNew')}
            </span>
          </button>
        )}
      </div>
      <div className="header-actions">
        {authSession && (
          <button
            type="button"
            className={`header-account ${authSession.identity.auth_type === 'guest' ? 'is-guest' : 'is-user'}`}
            title={authSession.identity.auth_type === 'guest' ? t('wechatLogin') : authSession.identity.display_name}
            onClick={authSession.identity.auth_type === 'guest'
              ? () => startWechatLogin('/chatBot')
              : undefined}
          >
            {authSession.identity.avatar_url
              ? <img src={authSession.identity.avatar_url} alt="" referrerPolicy="no-referrer" />
              : <span aria-hidden="true">
                {authSession.identity.auth_type === 'guest'
                  ? t('guestAvatarGlyph')
                  : t('wechatAvatarGlyph')}
              </span>}
            <b>{authSession.identity.auth_type === 'guest' ? t('wechatLogin') : authSession.identity.display_name}</b>
          </button>
        )}
        <a
          data-onboarding="github"
          className="header-icon-link"
          href={FEATURE_DOCUMENT_URL}
          target="_blank"
          rel="noreferrer noopener"
          aria-label={t('featureDocs')}
          title={t('featureDocs')}
        >
          <LogoGithubIcon />
        </a>
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
            title={rightPanelOpen ? t('collapsePanel') : t('expandPanel')}
            aria-pressed={rightPanelOpen}
            icon={rightPanelOpen ? <ChevronRightIcon /> : <ChevronLeftIcon />}
          />
        )}
        <Button
          data-onboarding="theme"
          className="theme-toggle"
          shape="circle"
          variant="text"
          size="medium"
          disabled={!connected}
          onClick={toggleTheme}
          aria-label={theme === 'dark' ? t('useLightTheme') : t('useDarkTheme')}
          title={theme === 'dark' ? t('useLightTheme') : t('useDarkTheme')}
          icon={theme === 'dark' ? <ModeLightIcon /> : <ModeDarkIcon />}
        />
      </div>
    </header>
  );
}
