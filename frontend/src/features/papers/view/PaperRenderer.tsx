import type { ChatMessage } from '../../chat/model';
import { useLanguage } from '../../../i18n';
import PaperInlineReader from './PaperInlineReader';
import PaperListCard from './PaperListCard';


export function PaperRenderer({ message }: { message: ChatMessage }) {
  const { t } = useLanguage();
  return <>
    {message.papers && message.papers.length > 0 && (
      <div style={{ marginTop: 12, width: '100%' }}>
        <PaperListCard message={message} />
      </div>
    )}
    {message.paperFileId && (
      <PaperInlineReader
        fileId={message.paperFileId}
        fileName={message.paperFileName || t('pdfDocument')}
        title={message.paperTitle || message.paperFileName || t('pdfReading')}
        assistantEnabled={Boolean(message.paperIsPaper)}
      />
    )}
  </>;
}
