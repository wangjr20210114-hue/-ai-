import { memo } from 'react';

import { useMessageBubbleController } from '../controller/useMessageBubbleController';
import {
  MessageBubbleView,
  type MessageBubbleViewProps,
} from './renderers/MessageBubbleView';

/** Thin feature View adapter: stateful actions live in the chat controller. */
function MessageBubble(props: MessageBubbleViewProps) {
  const controller = useMessageBubbleController({
    message: props.message,
    client: props.client,
    previousUserMessage: props.previousUserMessage,
    generationActive: props.generationActive,
    conversationId: props.conversationId,
  });
  return <MessageBubbleView {...props} controller={controller} />;
}

// Streaming tokens arrive many times per second. Unchanged bubbles keep stable
// props, so memo skips their reconciliation entirely.
export default memo(MessageBubble);
