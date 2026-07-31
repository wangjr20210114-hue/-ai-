import MarkdownRenderer from '../../../../components/common/MarkdownRenderer';
import type { ChatMessage } from '../../../../shared/types';


export function TextRenderer({
  message,
}: {
  message: ChatMessage;
}) {
  return (
    <MarkdownRenderer
      content={message.content}
      searchMeta={message.searchResults}
      streaming={message.streaming}
    />
  );
}
