import { useLayoutEffect, useRef, useState } from 'react';

import type { MessageBubbleController } from '../../controller/useMessageBubbleController';
import type { AssistantChainPosition } from '../../../../components/chat/assistantMessageChain';
import { hasTextSelectionInside } from '../../../../components/chat/scrollSelection';
import { useLanguage } from '../../../../i18n';
import type { ChatClient } from '../../../../services/chatClient';
import type { ChatMessage, ProactiveState } from '../../model';
import { MessageExtrasRenderer } from './MessageExtrasRenderer';
import { MessagePrimaryRenderer } from './MessagePrimaryRenderer';
import { selectRenderer } from './rendererRegistry';

export interface MessageBubbleViewProps {
  message: ChatMessage;
  client: React.RefObject<ChatClient | null>;
  assistantChainPosition?: AssistantChainPosition;
  isLastAiMessage: boolean;
  clarificationAnswered: boolean;
  previousUserMessage?: ChatMessage;
  generationActive: boolean;
  conversationId: string;
  proactive: ProactiveState | null;
  userAvatarUrl: string;
  authIsGuest: boolean;
}

interface Props extends MessageBubbleViewProps {
  controller: MessageBubbleController;
}

export function MessageBubbleView({
  message,
  client,
  assistantChainPosition = 'single',
  isLastAiMessage,
  clarificationAnswered,
  previousUserMessage,
  generationActive,
  conversationId,
  proactive,
  userAvatarUrl,
  authIsGuest,
  controller,
}: Props) {
  const { t } = useLanguage();
  const bubbleRef = useRef<HTMLDivElement>(null);
  const [followUpWidth, setFollowUpWidth] = useState<number>();
  const isUser = message.role === 'user';
  const isAssistantChain = !isUser && assistantChainPosition !== 'single';
  const assistantChainTail = assistantChainPosition === 'single'
    || assistantChainPosition === 'end';
  const isImageCreation = Boolean(
    message.streaming && message.skill?.intent === 'image',
  );
  const renderer = selectRenderer(message);

  useLayoutEffect(() => {
    if (isUser || message.streaming || !message.followUps?.length || !bubbleRef.current) {
      setFollowUpWidth(undefined);
      return;
    }
    const bubble = bubbleRef.current;
    const update = () => {
      if (hasTextSelectionInside(bubble, window.getSelection())) return;
      setFollowUpWidth(Number(bubble.getBoundingClientRect().width.toFixed(2)));
    };
    update();
    const settleTimer = window.setTimeout(update, 360);
    const observer = new ResizeObserver(update);
    observer.observe(bubble);
    return () => {
      window.clearTimeout(settleTimer);
      observer.disconnect();
    };
  }, [isUser, message.streaming, message.followUps]);

  return <div
    className={`msg-row ${isUser ? 'user' : 'ai'}${isAssistantChain ? ` assistant-chain-${assistantChainPosition}` : ''}`}
    data-message-id={message.id}
    data-message-role={message.role}
  >
    {!isUser && (assistantChainPosition === 'middle' || assistantChainPosition === 'end')
      ? <div className="msg-avatar-spacer" aria-hidden="true" />
      : <div className={`msg-avatar ${isUser ? 'user' : 'ai'}`}>
        {isUser
          ? <img
            src={userAvatarUrl}
            alt={t('me')}
            referrerPolicy="no-referrer"
          />
          : <img src="/floris-avatar.png" alt="Floris" />}
      </div>}
    <div className="msg-content-wrap">
      <div
        ref={bubbleRef}
        data-message-renderer={renderer.id}
        className={`msg-bubble ${isUser ? 'user' : 'ai'} ${message.failed ? 'is-error' : ''} ${isImageCreation ? 'is-image-generation' : ''}${isAssistantChain ? ` assistant-chain-bubble assistant-chain-bubble-${assistantChainPosition}` : ''}`}
      >
        {isUser
          ? <>
            {message.attachments?.map((attachment, index) => (
              attachment.kind === 'image' && attachment.url
                ? <figure className="message-attachment-image" key={`${attachment.storage_key || attachment.url}-${index}`}>
                  <img src={attachment.url} alt={attachment.name || t('pendingReferenceImage')} />
                  <figcaption>{attachment.name}</figcaption>
                </figure>
                : null
            ))}
            {message.content}
          </>
          : <MessagePrimaryRenderer
            message={message}
            client={client}
            bubbleRef={bubbleRef}
            clarificationAnswered={clarificationAnswered}
            generationActive={generationActive}
            conversationId={conversationId}
            previousUserMessage={previousUserMessage}
            proactive={proactive}
            assistantChainTail={assistantChainTail}
            authIsGuest={authIsGuest}
            controller={controller}
          />}
      </div>
      <MessageExtrasRenderer
        message={message}
        isUser={isUser}
        isLastAiMessage={isLastAiMessage}
        followUpWidth={followUpWidth}
        controller={controller}
      />
    </div>
  </div>;
}
