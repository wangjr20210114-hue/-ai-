import { Button, Tag, Tooltip } from 'tdesign-react';
import { ModeDarkIcon, ModeLightIcon } from 'tdesign-icons-react';
import { useAppDispatch, useAppState } from '../../store/appState';
import StatusIndicator from './StatusIndicator';
import { isEdgeOne } from '../../services/auth';

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
        >
          ☰
        </Button>
        <div
          style={{
            width: 30,
            height: 30,
            borderRadius: 9,
            background: 'linear-gradient(135deg, #2b5aed, #7c5cff)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            fontWeight: 700,
            fontSize: 15,
          }}
        >
          AI
        </div>
        <span className="brand-logo">元宝 Agent</span>
        <Tag size="small" variant="light" theme="primary" style={{ marginLeft: 4 }}>
          {isEdgeOne ? 'EdgeOne Makers · LangGraph' : '主动式 · 多能力'}
        </Tag>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <StatusIndicator />
        {onToggleRightPanel && (
          <Button
            className="right-panel-toggle"
            variant="text"
            size="small"
            onClick={onToggleRightPanel}
            aria-pressed={rightPanelOpen}
          >
            {rightPanelOpen ? '收起右栏' : '展开右栏'}
          </Button>
        )}
        <Tooltip content={theme === 'dark' ? '切换到浅色' : '切换到深色'}>
          <Button
            shape="circle"
            variant="text"
            size="small"
            onClick={toggleTheme}
            icon={theme === 'dark' ? <ModeLightIcon /> : <ModeDarkIcon />}
          />
        </Tooltip>
      </div>
    </header>
  );
}
