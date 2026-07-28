import { useLayoutEffect, useRef } from 'react';
import { useAppDispatch, useAppState } from '../../store/appState';
import MessageBubble from './MessageBubble';
import type { ChatClient } from '../../services/chatClient';
import { autoFollowAfterScroll, hasTextSelectionInside } from './scrollSelection';
import { useLanguage, type TranslationKey } from '../../i18n';
import { assistantChainPositions } from './assistantMessageChain';

const STARTERS: TranslationKey[] = [
  'starterAiNews',
  'starterHistoryBooks',
  'starterForbiddenCity',
  'starterQuickSort',
];

interface Props {
  client: React.RefObject<ChatClient | null>;
}

const prefersReducedMotion = () => (
  typeof window !== 'undefined'
  && typeof window.matchMedia === 'function'
  && window.matchMedia('(prefers-reduced-motion: reduce)').matches
);

/** 消息列表（居中），自动滚动到底部；空态展示引导。 */
export default function MessageList({ client }: Props) {
  const { messages, thinking, conversationId, proactive } = useAppState();
  const chainPositions = assistantChainPositions(
    thinking ? [...messages, { role: 'ai' as const }] : messages,
  );
  const thinkingChainPosition = thinking ? chainPositions[messages.length] : 'single';
  const generationActive = messages.some((item) => item.streaming);
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
    const grew = previousCountRef.current > 0 && messages.length > previousCountRef.current;
    // Sending a message of your own always rejoins the live edge.
    const ownMessageSent = grew && messages[messages.length - 1]?.role === 'user';
    if (ownMessageSent) shouldStickToBottomRef.current = true;
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
      // Structural additions (a sent question, a new answer) glide to the
      // bottom; streamed tokens keep the viewport anchored instantly so the
      // smooth animation never restarts mid-flight.
      if (grew && !prefersReducedMotion()) {
        container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
      } else {
        container.scrollTop = container.scrollHeight;
      }
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
          <div className="chat-empty-title">{t('appTitle')}</div>
          <div className="chat-empty-sub">
            {t('appWelcome')}
            <br />
            {t('appCapabilities')}
          </div>
          <div className="chat-empty-chips">
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
        {messages.map((m, index) => {
          const previousUserMessage = index > 0
            ? [...messages.slice(0, index)].reverse().find((item) => item.role === 'user')
            : undefined;
          return (
            <MessageBubble
              key={m.id}
              message={m}
              client={client}
              assistantChainPosition={chainPositions[index]}
              isLastAiMessage={m.role === 'ai' && index === messages.length - 1}
              clarificationAnswered={Boolean(m.clarification)
                && (Boolean(m.clarificationAnswered)
                  || messages.slice(index + 1).some((item) => item.role === 'user'))}
              previousUserMessage={previousUserMessage}
              generationActive={generationActive}
              conversationId={conversationId}
              proactive={proactive}
            />
          );
        })}

        {thinking && (
          <div className={`msg-row ai${thinkingChainPosition !== 'single' ? ` assistant-chain-${thinkingChainPosition}` : ''}`}>
            {thinkingChainPosition === 'middle' || thinkingChainPosition === 'end'
              ? <div className="msg-avatar-spacer" aria-hidden="true" />
              : <div className="msg-avatar ai"><img src="/floris-avatar.png" alt="Floris" /></div>}
            <div className={`msg-bubble ai${thinkingChainPosition !== 'single' ? ` assistant-chain-bubble assistant-chain-bubble-${thinkingChainPosition}` : ''}`}>
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
