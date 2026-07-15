import { useLayoutEffect, useRef } from 'react';
import { useAppDispatch, useAppState } from '../../store/appState';
import MessageBubble from './MessageBubble';
import type { ChatClient } from '../../services/chatClient';

const STARTERS = [
  '最近AI有什么新进展',
  '帮我推荐几本明朝历史的书',
  '北京故宫有什么好玩的',
  '用Python写一个快速排序',
];

interface Props {
  client: React.RefObject<ChatClient | null>;
}

/** 消息列表（居中），自动滚动到底部；空态展示引导。 */
export default function MessageList({ client }: Props) {
  const { messages, thinking } = useAppState();
  const dispatch = useAppDispatch();
  const endRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const previousCountRef = useRef(0);
  const shouldStickToBottomRef = useRef(true);

  useLayoutEffect(() => {
    const container = scrollRef.current;
    if (!container) return;
    const isInitialRestore = previousCountRef.current === 0 && messages.length > 0;
    const hasNewMessage = messages.length > previousCountRef.current;
    if (isInitialRestore) {
      // Run before paint so a restored task opens at the bottom without a visible scroll.
      container.scrollTop = container.scrollHeight;
      requestAnimationFrame(() => {
        container.scrollTop = container.scrollHeight;
      });
    } else if (hasNewMessage || shouldStickToBottomRef.current) {
      // Status labels and streamed tokens update often. Keep the viewport anchored
      // without restarting a smooth-scroll animation on every text change.
      container.scrollTop = container.scrollHeight;
    }
    previousCountRef.current = messages.length;
  }, [messages, thinking]);

  const trackScrollPosition = () => {
    const container = scrollRef.current;
    if (!container) return;
    shouldStickToBottomRef.current = container.scrollHeight - container.scrollTop - container.clientHeight < 80;
  };

  if (messages.length === 0) {
    return (
      <div className="chat-scroll" ref={scrollRef}>
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
    <div className="chat-scroll" ref={scrollRef} onScroll={trackScrollPosition}>
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
