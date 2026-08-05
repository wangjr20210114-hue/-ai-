import type { ChatMessage } from '../../model';
import { PaperRenderer as PapersView } from '../../../papers/view';


export function PaperRenderer({ message }: { message: ChatMessage }) {
  return <PapersView message={message} />;
}
