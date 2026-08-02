import { useCallback, useEffect, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from 'react';
import { useChatController } from '../features/chat/controller/useChatController';
import { useAppState } from '../store/appState';
import Header from '../components/common/Header';
import ChatInterface from '../components/chat/ChatInterface';
import { EdgeOnePlatformPanel } from '../features/settings/view';
import type { ChatClient } from '../services/chatClient';
import type { RefObject } from 'react';
import ConversationSidebar from '../components/conversation/ConversationSidebar';
import { useLanguage } from '../i18n';
import { OPEN_RIGHT_WORKSPACE_EVENT } from '../services/workspaceEvents';
import FlorisOnboarding from '../components/onboarding/FlorisOnboarding';
import AuthDialog from '../features/auth/view/AuthDialog';

const LEFT_PANE_MIN = 190;
const LEFT_PANE_MAX = 420;
const RIGHT_PANE_MIN = 280;
const RIGHT_PANE_MAX = 520;
const CENTER_PANE_MIN = 440;
const COMPACT_WORKSPACE_QUERY = '(max-width: 860px)';

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), Math.max(min, max));
}

function storedNumber(key: string, fallback: number) {
  try {
    const value = Number(localStorage.getItem(key));
    return Number.isFinite(value) && value > 0 ? value : fallback;
  } catch {
    return fallback;
  }
}

function AppLayout({ client }: { client: RefObject<ChatClient | null> }) {
  const { theme, connected } = useAppState();
  const { t } = useLanguage();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [leftPaneWidth, setLeftPaneWidth] = useState(() => storedNumber('yuanbao-left-pane-width', 252));
  const [rightPaneWidth, setRightPaneWidth] = useState(() => storedNumber('yuanbao-right-pane-width', 340));
  const [rightPanelOpen, setRightPanelOpen] = useState(() => {
    if (window.matchMedia(COMPACT_WORKSPACE_QUERY).matches) return false;
    try {
      return localStorage.getItem('yuanbao-right-panel-open') !== 'false';
    } catch {
      return true;
    }
  });
  const bodyRef = useRef<HTMLDivElement>(null);
  const revealOnboardingArea = useCallback((area: 'sidebar' | 'workspace' | 'header') => {
    const compact = window.matchMedia(COMPACT_WORKSPACE_QUERY).matches;
    if (area === 'sidebar') {
      setSidebarOpen(true);
      if (compact) setRightPanelOpen(false);
      return;
    }
    if (area === 'workspace') {
      setSidebarOpen(false);
      setRightPanelOpen(true);
      return;
    }
    if (compact) {
      setSidebarOpen(false);
      setRightPanelOpen(false);
    }
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute('theme-mode', theme);
  }, [theme]);

  useEffect(() => {
    const compactWorkspace = window.matchMedia(COMPACT_WORKSPACE_QUERY);
    const closePanelForCompactLayout = (event: MediaQueryListEvent) => {
      if (event.matches) setRightPanelOpen(false);
    };
    compactWorkspace.addEventListener('change', closePanelForCompactLayout);
    return () => compactWorkspace.removeEventListener('change', closePanelForCompactLayout);
  }, []);

  useEffect(() => {
    const openRightWorkspace = () => setRightPanelOpen(true);
    window.addEventListener(OPEN_RIGHT_WORKSPACE_EVENT, openRightWorkspace);
    return () => window.removeEventListener(OPEN_RIGHT_WORKSPACE_EVENT, openRightWorkspace);
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem('yuanbao-left-pane-width', String(leftPaneWidth));
      localStorage.setItem('yuanbao-right-pane-width', String(rightPaneWidth));
      if (!window.matchMedia(COMPACT_WORKSPACE_QUERY).matches) {
        localStorage.setItem('yuanbao-right-panel-open', String(rightPanelOpen));
      }
    } catch {
      // Local preferences are optional.
    }
  }, [leftPaneWidth, rightPaneWidth, rightPanelOpen]);

  const startResize = (side: 'left' | 'right') => (event: ReactPointerEvent<HTMLDivElement>) => {
    if (window.innerWidth <= 1180) return;
    event.preventDefault();
    const startX = event.clientX;
    const initialWidth = side === 'left' ? leftPaneWidth : rightPaneWidth;

    const resize = (pointerEvent: PointerEvent) => {
      const bodyWidth = bodyRef.current?.getBoundingClientRect().width || window.innerWidth;
      if (side === 'left') {
        const max = Math.min(LEFT_PANE_MAX, bodyWidth - (rightPanelOpen ? rightPaneWidth : 0) - CENTER_PANE_MIN);
        setLeftPaneWidth(clamp(initialWidth + pointerEvent.clientX - startX, LEFT_PANE_MIN, max));
      } else {
        const max = Math.min(RIGHT_PANE_MAX, bodyWidth - leftPaneWidth - CENTER_PANE_MIN);
        setRightPaneWidth(clamp(initialWidth + startX - pointerEvent.clientX, RIGHT_PANE_MIN, max));
      }
    };

    const stop = () => {
      document.documentElement.classList.remove('is-resizing-workspace');
      window.removeEventListener('pointermove', resize);
      window.removeEventListener('pointerup', stop);
      window.removeEventListener('pointercancel', stop);
    };

    document.documentElement.classList.add('is-resizing-workspace');
    window.addEventListener('pointermove', resize);
    window.addEventListener('pointerup', stop);
    window.addEventListener('pointercancel', stop);
  };

  const resizeWithKeyboard = (side: 'left' | 'right') => (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    event.preventDefault();
    const delta = event.key === 'ArrowRight' ? 16 : -16;
    if (side === 'left') {
      setLeftPaneWidth((width) => clamp(width + delta, LEFT_PANE_MIN, LEFT_PANE_MAX));
    } else {
      setRightPaneWidth((width) => clamp(width - delta, RIGHT_PANE_MIN, RIGHT_PANE_MAX));
    }
  };

  const workspaceStyle = {
    '--left-pane-width': `${leftPaneWidth}px`,
    '--right-pane-width': `${rightPaneWidth}px`,
  } as CSSProperties;

  return (
    <div className="app-shell">
      <Header
        onToggleSidebar={() => setSidebarOpen((value) => !value)}
        rightPanelOpen={rightPanelOpen}
        onToggleRightPanel={() => setRightPanelOpen((value) => !value)}
      />
      <div
        className="app-body"
        ref={bodyRef}
        style={workspaceStyle}
      >
        <ConversationSidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
        <div
          className="workspace-resizer workspace-resizer-left"
          role="separator"
          aria-label={t('resizeConversationList')}
          aria-orientation="vertical"
          tabIndex={0}
          onPointerDown={startResize('left')}
          onKeyDown={resizeWithKeyboard('left')}
        />
        <ChatInterface client={client} />
        <div
          className={`workspace-resizer workspace-resizer-right ${rightPanelOpen ? 'is-open' : 'is-closed'}`}
              role="separator"
              aria-label={t('resizeWorkspace')}
              aria-orientation="vertical"
              tabIndex={0}
              onPointerDown={startResize('right')}
              onKeyDown={resizeWithKeyboard('right')}
        />
        <div className={`right-workspace-shell ${rightPanelOpen ? 'is-open' : 'is-closed'}`} aria-hidden={!rightPanelOpen}>
          <EdgeOnePlatformPanel />
        </div>
      </div>
      <FlorisOnboarding connected={connected} revealArea={revealOnboardingArea} />
      <AuthDialog />
    </div>
  );
}

function App() {
  return <AppLayout client={useChatController()} />;
}

export default App;
