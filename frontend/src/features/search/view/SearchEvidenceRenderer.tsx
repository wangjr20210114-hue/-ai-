import MarkdownRenderer from '../../../components/common/MarkdownRenderer';
import type { ChatMessage } from '../../../shared/types';


export function SearchEvidenceRenderer({ message }: { message: ChatMessage }) {
  if (!message.searchResults) return null;
  return (
    <MarkdownRenderer
      content={message.content}
      searchMeta={message.searchResults}
      streaming={message.streaming}
    />
  );
}
