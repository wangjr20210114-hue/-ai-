import { Button, Tooltip } from 'tdesign-react';
import { ChatBubbleHistoryIcon, ChevronLeftIcon, ChevronRightIcon, ModeDarkIcon, ModeLightIcon } from 'tdesign-icons-react';
import { useAppDispatch, useAppState } from '../../store/appState';
import StatusIndicator from './StatusIndicator';

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
  const { theme } = useAppState();
  const dispatch = useAppDispatch();

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
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <Button
          className="conversation-menu-button"
          shape="circle"
          variant="text"
          size="small"
          onClick={onToggleSidebar}
          aria-label="打开历史对话"
          icon={<ChatBubbleHistoryIcon />}
        >
        </Button>
        <span className="brand-logo">元宝 Agent</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <StatusIndicator />
        {onToggleRightPanel && (
          <Tooltip content={rightPanelOpen ? '收起右栏' : '展开右栏'}>
            <Button
              className="right-panel-toggle"
              shape="circle"
              variant="text"
              size="medium"
              onClick={onToggleRightPanel}
              aria-label={rightPanelOpen ? '收起右栏' : '展开右栏'}
              aria-pressed={rightPanelOpen}
              icon={rightPanelOpen ? <ChevronRightIcon /> : <ChevronLeftIcon />}
            />
          </Tooltip>
        )}
        <Tooltip content={theme === 'dark' ? '切换到浅色' : '切换到深色'}>
          <Button
            className="theme-toggle"
            shape="circle"
            variant="text"
            size="medium"
            onClick={toggleTheme}
            icon={theme === 'dark' ? <ModeLightIcon /> : <ModeDarkIcon />}
          />
        </Tooltip>
      </div>
    </header>
  );
}
