import { useAppState } from '../../store/appState';
import { useLanguage } from '../../i18n';

/** 连接状态指示器。 */
export default function StatusIndicator() {
  const { connected } = useAppState();
  const { t } = useLanguage();
  if (!connected) return null;
  return (
    <span
      className="connection-status"
      style={{
        fontSize: 12,
        color: 'var(--app-text-2)',
        display: 'inline-flex',
        alignItems: 'center',
      }}
    >
      <span
        className="status-dot"
        style={{ background: '#00a870' }}
      />
      {t('connected')}
    </span>
  );
}
