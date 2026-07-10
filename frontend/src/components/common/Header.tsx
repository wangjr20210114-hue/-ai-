import { Button, Tag, Tooltip } from 'tdesign-react';
import { ModeDarkIcon, ModeLightIcon } from 'tdesign-icons-react';
import { useAppDispatch, useAppState } from '../../store/appState';
import StatusIndicator from './StatusIndicator';

const THEME_KEY = 'travel-theme';

/** 顶部导航栏。 */
export default function Header() {
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
          主动式 · 多能力
        </Tag>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <StatusIndicator />
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
