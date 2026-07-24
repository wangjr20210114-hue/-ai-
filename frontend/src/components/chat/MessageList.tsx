import { useLayoutEffect, useRef } from 'react';
import { useAppDispatch, useAppState } from '../../store/appState';
import MessageBubble from './MessageBubble';
import type { ChatClient } from '../../services/chatClient';
import { autoFollowAfterScroll, hasTextSelectionInside } from './scrollSelection';
import { useLanguage, type TranslationKey } from '../../i18n';

const STARTERS: TranslationKey[] = [
  'starterAiNews',
  'starterHistoryBooks',
  'starterForbiddenCity',
  'starterQuickSort',
];

interface Props {
  client: React.RefObject<ChatClient | null>;
}

/** 消息列表（居中），自动滚动到底部；空态展示引导。 */
export default function MessageList({ client }: Props) {
  const { messages, thinking } = useAppState();
  const { t } = useLanguage();
  const dispatch = useAppDispatch();
  const endRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const previousCountRef = useRef(0);
  const shouldStickToBottomRef = useRef(true);
  const previousScrollTopRef = useRef(0);

  useLayoutEffect(() => {
    const container = scrollRef.current;
    if (!container) return;
    const isInitialRestore = previousCountRef.current === 0 && messages.length > 0;
    if (isInitialRestore) {
      // Run before paint so a restored task opens at the bottom without a visible scroll.
      container.scrollTop = container.scrollHeight;
      previousScrollTopRef.current = container.scrollTop;
      requestAnimationFrame(() => {
        container.scrollTop = container.scrollHeight;
        previousScrollTopRef.current = container.scrollTop;
      });
    } else if (hasTextSelectionInside(container, window.getSelection())) {
      // Never move the viewport while the user is selecting/copying an answer.
      shouldStickToBottomRef.current = false;
    } else if (shouldStickToBottomRef.current) {
      // Status labels and streamed tokens update often. Keep the viewport anchored
      // without restarting a smooth-scroll animation on every text change.
      container.scrollTop = container.scrollHeight;
      previousScrollTopRef.current = container.scrollTop;
    }
    previousCountRef.current = messages.length;
  }, [messages, thinking]);

  const trackScrollPosition = () => {
    const container = scrollRef.current;
    if (!container) return;
    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    shouldStickToBottomRef.current = autoFollowAfterScroll(
      shouldStickToBottomRef.current,
      previousScrollTopRef.current,
      container.scrollTop,
      distanceFromBottom,
    );
    previousScrollTopRef.current = container.scrollTop;
  };

  const stopAutoFollow = () => {
    shouldStickToBottomRef.current = false;
  };

  const finishPointerInteraction = () => {
    const container = scrollRef.current;
    if (!container || hasTextSelectionInside(container, window.getSelection())) return;
    trackScrollPosition();
  };

  if (messages.length === 0) {
    return (
      <div className="chat-scroll" ref={scrollRef}>
        <div className="chat-empty">
          <div className="chat-empty-logo"><img src="/floris-avatar.png" alt="Floris" /></div>
          <div style={{ fontSize: 20, fontWeight: 600, color: 'var(--app-text)' }}>
            {t('appTitle')}
          </div>
          <div style={{ fontSize: 13.5, maxWidth: 420, lineHeight: 1.8 }}>
            {t('appWelcome')}
            <br />
            {t('appCapabilities')}
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
            {STARTERS.map((key) => (
              <button type="button" key={key} className="chip" onClick={() => dispatch({ type: 'SET_DRAFT', payload: t(key) })}>
                {t(key)}
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className="chat-scroll"
      ref={scrollRef}
      onScroll={trackScrollPosition}
      onWheel={(event) => { if (event.deltaY < 0) stopAutoFollow(); }}
      onTouchStart={stopAutoFollow}
      onPointerDown={(event) => {
        const target = event.target as Element;
        if (event.target === event.currentTarget || target.closest('.msg-bubble')) stopAutoFollow();
      }}
      onPointerUp={finishPointerInteraction}
      onCopy={stopAutoFollow}
    >
      <div className="chat-inner">
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} client={client} />
        ))}

        {thinking && (
          <div className="msg-row ai">
            <div className="msg-avatar ai"><img src="/floris-avatar.png" alt="Floris" /></div>
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
