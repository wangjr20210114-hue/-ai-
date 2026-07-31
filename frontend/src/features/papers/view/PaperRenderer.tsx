import PaperListCard from '../../../components/paper/PaperListCard';
import type { ChatMessage } from '../../../shared/types';


export function PaperRenderer({ message }: { message: ChatMessage }) {
  if (!message.papers?.length) return null;
  return <PaperListCard message={message} />;
}
