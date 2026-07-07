import { useEffect, useRef } from 'react';
import { useAppDispatch, useAppState } from '../../store/AppContext';
import MessageBubble from './MessageBubble';
import type { WSClient } from '../../services/websocket';

const STARTERS = [
  '我想去杭州旅游，3天行程',
  '明天下午3点和团队开个需求评审会',
  '最近AI有什么新进展',
  '这篇英文论文好难懂，帮我看看',
];

interface Props {
  client: React.RefObject<WSClient | null>;
}

/** 消息列表（居中），自动滚动到底部；空态展示引导。 */
export default function MessageList({ client }: Props) {
  const { messages, thinking } = useAppState();
  const dispatch = useAppDispatch();
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, thinking]);

  if (messages.length === 0) {
    return (
      <div className="chat-scroll">
        <div className="chat-empty">
          <div className="chat-empty-logo">AI</div>
          <div style={{ fontSize: 20, fontWeight: 600, color: 'var(--app-text)' }}>
            旅游 Agent
          </div>
          <div style={{ fontSize: 13.5, maxWidth: 420, lineHeight: 1.8 }}>
            和我对话即可。我是元宝主动式 Agent，
            <br />
            支持旅游规划、会议创建、新闻搜索、翻译、论文助读、AI 生图。
          </div>
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: 10,
              justifyContent: 'center',
              marginTop: 8,
              maxWidth: 520,
            }}
          >
            {STARTERS.map((s) => (
              <span key={s} className="chip" onClick={() => dispatch({ type: 'SET_DRAFT', payload: s })}>
                {s}
              </span>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-scroll">
      <div className="chat-inner">
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} client={client} />
        ))}

        {thinking && (
          <div className="msg-row ai">
            <div className="msg-avatar ai">AI</div>
            <div className="msg-bubble ai">
              <span className="typing-dots">
                <span />
                <span />
                <span />
              </span>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>
    </div>
  );
}
