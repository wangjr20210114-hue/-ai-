/**
 * PaperListCard：论文列表卡片 + 内联阅读器。
 * 使用统一的 InfoCard 组件展示论文信息。
 */
import { useState } from 'react';
import { Button, MessagePlugin } from 'tdesign-react';
import { DownloadIcon, FullscreenIcon } from 'tdesign-icons-react';
import type { ChatMessage, PaperInfo } from '../../types';
import { downloadPaper, fetchPaperFile } from '../../services/paperApi';
import { dedupePapers } from '../../services/paperUtils';
import InfoCard from '../common/InfoCard';
import PaperFullReader from './PaperFullReader';
import { useLanguage } from '../../i18n';

interface Props {
  message: ChatMessage;
}

interface DownloadedPaper {
  fileId: string;
  title: string;
  fileName: string;
  arxivId?: string;
}

export default function PaperListCard({ message }: Props) {
  const { t } = useLanguage();
  const papers = dedupePapers(message.papers || []);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [downloaded, setDownloaded] = useState<Record<string, DownloadedPaper>>({});
  const [fullReader, setFullReader] = useState<DownloadedPaper | null>(null);

  const ensureDownloaded = async (paper: PaperInfo): Promise<DownloadedPaper | null> => {
    if (downloaded[paper.arxiv_id]) return downloaded[paper.arxiv_id];
    setDownloadingId(paper.arxiv_id);
    try {
      const result = await downloadPaper(paper.arxiv_id, paper.title, paper.pdf_url);
      if (result.error) {
        MessagePlugin.warning(t('downloadFailed'));
        return null;
      }
      const stored = {
          fileId: result.file_id,
          title: result.title,
          fileName: result.filename,
          arxivId: paper.arxiv_id,
        };
      setDownloaded(prev => ({ ...prev, [paper.arxiv_id]: stored }));
      return stored;
    } catch {
      MessagePlugin.error(t('downloadFailed'));
      return null;
    } finally {
      setDownloadingId(null);
    }
  };

  const openReader = async (paper: PaperInfo) => {
    const stored = await ensureDownloaded(paper);
    if (stored) setFullReader(stored);
  };

  const savePdf = async (paper: PaperInfo) => {
    const stored = await ensureDownloaded(paper); if (!stored) return;
    try {
      const response = await fetchPaperFile(stored.fileId);
      if (!response.ok) throw new Error(t('fileDownloadFailed'));
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a'); link.href = url; link.download = stored.fileName || `${paper.title}.pdf`; link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { MessagePlugin.error(t('fileDownloadFailed')); }
  };

  if (papers.length === 0) return null;

  return (
    <div>
      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--app-text-3)', marginBottom: 6 }}>
        {t('papersFound', { count: papers.length })}
      </div>
      {papers.map((paper, i) => {
        return (
          <div key={paper.arxiv_id + i}>
            <InfoCard
              type="paper"
              title={paper.title}
              snippet={paper.abstract_zh}
              sourceLabel={t('sourcePaper')}
              tags={[
                { label: String(paper.year) },
                ...(paper.citations && paper.citations.toLowerCase() !== 'arxiv' ? [{ label: paper.citations }] : []),
                { label: paper.arxiv_id.startsWith('webpdf-') ? t('publicPdf') : `arXiv:${paper.arxiv_id}` },
              ]}
              extra={<div className="paper-card-actions">
                <Button size="small" theme="primary" loading={downloadingId === paper.arxiv_id} icon={<FullscreenIcon />} onClick={() => void openReader(paper)}>{t('fullscreenReading')}</Button>
                <Button size="small" variant="outline" loading={downloadingId === paper.arxiv_id} icon={<DownloadIcon />} onClick={() => void savePdf(paper)}>{t('downloadPaper')}</Button>
                {!paper.arxiv_id.startsWith('webpdf-') && <a href={paper.arxiv_url} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()}><Button size="small" variant="text">arXiv</Button></a>}
              </div>}
            />
          </div>
        );
      })}

      {fullReader && (
        <PaperFullReader
          fileId={fullReader.fileId}
          title={fullReader.title}
          arxivId={fullReader.arxivId}
          onClose={() => setFullReader(null)}
        />
      )}
    </div>
  );
}
