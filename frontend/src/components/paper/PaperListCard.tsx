/**
 * Compact arXiv discovery cards. The only actions are entering the in-app
 * paper assistant and opening the canonical arXiv page.
 */
import { useState } from 'react';
import { Button, MessagePlugin } from 'tdesign-react';
import { BookOpenIcon, JumpIcon } from 'tdesign-icons-react';
import type { ChatMessage, PaperInfo } from '../../types';
import { downloadPaper } from '../../services/paperApi';
import { dedupePapers, paperArxivHref, paperSourceHref } from '../../services/paperUtils';
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

function paperDownloadId(paper: PaperInfo): string {
  if (paper.arxiv_id) return paper.arxiv_id;
  if (!paper.pdf_url) return '';
  let hash = 2166136261;
  for (const character of paper.pdf_url) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return `webpdf-${(hash >>> 0).toString(16)}`;
}

export default function PaperListCard({ message }: Props) {
  const { t } = useLanguage();
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
      const result = await downloadPaper(downloadId, paper.title, paper.pdf_url);
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
    if (stored) setFullReader(stored);
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
          const readerAvailable = Boolean(
            downloadId
            && (paper.pdf_url || !downloadId.startsWith('webpdf-')),
          );
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
                  disabled={!readerAvailable}
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

      {fullReader && (
        <PaperFullReader
          fileId={fullReader.fileId}
          title={fullReader.title}
          arxivId={fullReader.arxivId}
          onClose={() => setFullReader(null)}
        />
      )}
    </section>
  );
}
