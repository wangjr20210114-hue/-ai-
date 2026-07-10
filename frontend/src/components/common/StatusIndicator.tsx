import { useAppState } from '../../store/appState';

/** 连接状态指示器。 */
export default function StatusIndicator() {
  const { connected } = useAppState();
  return (
    <span
      style={{
        fontSize: 12,
        color: 'var(--app-text-2)',
        display: 'inline-flex',
        alignItems: 'center',
      }}
    >
      <span
        className="status-dot"
        style={{ background: connected ? '#00a870' : '#e34d59' }}
      />
      {connected ? '已连接' : '连接中…'}
    </span>
  );
}
