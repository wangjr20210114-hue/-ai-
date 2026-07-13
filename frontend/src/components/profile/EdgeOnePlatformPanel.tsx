import { Tag } from 'tdesign-react';
import { CloudIcon, SearchIcon, ChatIcon, ChartIcon } from 'tdesign-icons-react';
import { useAppState } from '../../store/appState';

const capabilities = [
  { icon: <ChatIcon />, label: 'LangGraph Runtime', detail: '平台托管运行与中止' },
  { icon: <CloudIcon />, label: 'Conversation Store', detail: '检查点与会话恢复' },
  { icon: <SearchIcon />, label: 'Makers Tools', detail: '内置联网搜索工具' },
  { icon: <ChartIcon />, label: 'Tracing', detail: '全链路运行追踪' },
];

export default function EdgeOnePlatformPanel() {
  const { conversationId, connected } = useAppState();

  return (
    <aside className="my-panel">
      <div className="my-panel-card">
        <div className="section-title" style={{ marginBottom: 10 }}>
          EdgeOne Makers
          <Tag
            size="small"
            theme={connected ? 'success' : 'warning'}
            variant="light"
            style={{ marginLeft: 'auto' }}
          >
            {connected ? '已连接' : '连接中'}
          </Tag>
        </div>
        <div style={{ fontSize: 12, color: 'var(--app-text-2)', lineHeight: 1.7 }}>
          Agent 运行时、模型网关、会话记忆和追踪均由 Makers 托管，本页不再依赖本地常驻服务器。
        </div>
      </div>

      <div className="my-panel-card">
        <div className="section-title" style={{ marginBottom: 8 }}>平台能力</div>
        <div style={{ display: 'grid', gap: 8 }}>
          {capabilities.map((item) => (
            <div
              key={item.label}
              style={{
                display: 'grid',
                gridTemplateColumns: '28px 1fr',
                gap: 8,
                alignItems: 'center',
                padding: '9px 10px',
                borderRadius: 9,
                background: 'var(--app-bg)',
                border: '1px solid var(--app-border)',
              }}
            >
              <span style={{ color: 'var(--app-primary)', display: 'flex' }}>{item.icon}</span>
              <span>
                <span style={{ display: 'block', fontSize: 12, fontWeight: 600 }}>{item.label}</span>
                <span style={{ display: 'block', fontSize: 11, color: 'var(--app-text-3)', marginTop: 2 }}>
                  {item.detail}
                </span>
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="my-panel-card">
        <div className="section-title" style={{ marginBottom: 6 }}>当前会话</div>
        <code style={{ fontSize: 11, color: 'var(--app-text-3)', wordBreak: 'break-all' }}>
          {conversationId}
        </code>
      </div>
    </aside>
  );
}
