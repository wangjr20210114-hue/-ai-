/**
 * Compact scholarly discovery cards. The only actions are entering the in-app
 * paper assistant and opening the canonical source page.
 */
import { useState } from 'react';
import { createPortal } from 'react-dom';
import { Button, MessagePlugin } from 'tdesign-react';
import { BookOpenIcon, JumpIcon } from 'tdesign-icons-react';
import type { ChatMessage, PaperInfo } from '../../../shared/types';
import {
  dedupePapers,
  paperArxivHref,
  paperDownloadId,
  paperSourceHref,
} from '../../../services/paperUtils';
import PaperFullReader from './PaperFullReader';
import { useLanguage } from '../../../i18n';
import { usePapersController } from '../controller/usePapersController';

interface Props {
  message: ChatMessage;
}

interface DownloadedPaper {
  fileId: string;
  title: string;
  fileName: string;
  arxivId?: string;
  fileSize?: number;
  partSize?: number;
}

export default function PaperListCard({ message }: Props) {
  const { t } = useLanguage();
  const { api: { downloadPaper, preloadPaperFile } } = usePapersController();
  const papers = dedupePapers(message.papers || []);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [downloaded, setDownloaded] = useState<Record<string, DownloadedPaper>>({});
  const [fullReader, setFullReader] = useState<DownloadedPaper | null>(null);

  const ensureDownloaded = async (paper: PaperInfo): Promise<DownloadedPaper | null> => {
    const downloadId = paperDownloadId(paper);
    if (!downloadId) return null;
    if (downloaded[downloadId]) return downloaded[downloadId];
    setDownloadingId(downloadId);
    try {
      const result = await downloadPaper(
        downloadId,
        paper.title,
        paper.pdf_url,
        paper.source_url || paper.arxiv_url,
      );
      if (result.error) {
        if (result.code === 'public_pdf_unavailable') {
          MessagePlugin.warning(t('paperPublicPdfUnavailable'));
        } else if (result.code === 'paper_download_failed') {
          MessagePlugin.warning(t('paperDownloadUnavailable'));
        } else if (result.code === 'paper_timeout') {
          MessagePlugin.warning(t('paperResolveTimedOut'));
        } else {
          MessagePlugin.warning(t('paperStartFailed', {
            reason: result.error || t('downloadFailed'),
          }));
        }
        return null;
      }
      const stored = {
        fileId: result.file_id,
        title: result.title,
        fileName: result.filename,
        arxivId: result.arxiv_id || paper.arxiv_id,
        fileSize: result.file_size,
        partSize: result.part_size,
      };
      setDownloaded((previous) => ({
        ...previous,
        [downloadId]: stored,
      }));
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
    if (stored) {
      preloadPaperFile(stored.fileId, {
        size: stored.fileSize,
        partSize: stored.partSize,
      });
      setFullReader(stored);
    }
  };

  if (papers.length === 0) return null;

  return (
    <section className="paper-results" aria-label={t('paperResultsHeading', { count: papers.length })}>
      <header className="paper-results-heading">
        <span className="paper-results-mark"><BookOpenIcon /></span>
        <span>{t('paperResultsHeading', { count: papers.length })}</span>
      </header>

      <div className="paper-results-list">
        {papers.map((paper, index) => {
          const arxivHref = paperArxivHref(paper);
          const sourceHref = paperSourceHref(paper);
          const downloadId = paperDownloadId(paper);
          return (
            <article className="paper-discovery-card" key={`${paper.arxiv_id || paper.source_url || paper.title}-${index}`}>
              <div className="paper-discovery-meta">
                <span className="paper-discovery-source">{paper.source || 'arXiv'}</span>
                {paper.year > 0 && <span>{paper.year}</span>}
                {paper.arxiv_id && !paper.arxiv_id.startsWith('webpdf-') && <span className="paper-discovery-id">{paper.arxiv_id}</span>}
              </div>

              <h3>{paper.title}</h3>
              {paper.authors && (
                <p className="paper-discovery-authors">{paper.authors}</p>
              )}
              {paper.abstract_zh && (
                <p className="paper-discovery-abstract">{paper.abstract_zh}</p>
              )}

              <footer className="paper-discovery-actions">
                <Button
                  className="paper-assistant-button"
                  theme="primary"
                  loading={downloadingId === downloadId}
                  disabled={!downloadId}
                  icon={<BookOpenIcon />}
                  onClick={() => void openReader(paper)}
                >
                  {t('startPaperAssistant')}
                </Button>
                {sourceHref ? (
                  <a
                    className="paper-arxiv-button"
                    href={sourceHref}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <JumpIcon />
                    <span>{arxivHref ? t('openArxiv') : t('openPaper')}</span>
                  </a>
                ) : (
                  <span className="paper-arxiv-button is-disabled" aria-disabled="true">
                    <JumpIcon />
                    <span>{t('openPaper')}</span>
                  </span>
                )}
              </footer>
            </article>
          );
        })}
      </div>

      {fullReader && createPortal(
        <PaperFullReader
          fileId={fullReader.fileId}
          title={fullReader.title}
          arxivId={fullReader.arxivId}
          fileSize={fullReader.fileSize}
          partSize={fullReader.partSize}
          onClose={() => setFullReader(null)}
        />,
        document.body,
      )}
    </section>
  );
}
