/**
 * PaperListCard：论文列表卡片 + 内联阅读器。
 * 使用统一的 InfoCard 组件展示论文信息。
 */
import { useState } from 'react';
import { MessagePlugin } from 'tdesign-react';
import type { PaperInfo, ChatMessage } from '../../types';
import { downloadPaper } from '../../services/paperApi';
import InfoCard from '../common/InfoCard';
import PaperInlineReader from './PaperInlineReader';
import PaperFullReader from './PaperFullReader';

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
  const papers: PaperInfo[] = message.papers || [];
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [downloaded, setDownloaded] = useState<Record<string, DownloadedPaper>>({});
  const [fullReader, setFullReader] = useState<DownloadedPaper | null>(null);

  const handleDownload = async (paper: PaperInfo) => {
    setDownloadingId(paper.arxiv_id);
    MessagePlugin.info(`正在下载 ${paper.title.slice(0, 30)}...`);
    try {
      const result = await downloadPaper(paper.arxiv_id, paper.title);
      if (result.error) {
        MessagePlugin.warning(result.error);
        return;
      }
      setDownloaded(prev => ({
        ...prev,
        [paper.arxiv_id]: {
          fileId: result.file_id,
          title: result.title,
          fileName: result.filename,
          arxivId: paper.arxiv_id,
        },
      }));
      MessagePlugin.success('论文已下载，可在全屏阅读中收藏');
    } catch {
      MessagePlugin.error('下载失败');
    } finally {
      setDownloadingId(null);
    }
  };

  if (papers.length === 0) return null;

  return (
    <div>
      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--app-text-3)', marginBottom: 6 }}>
        📄 找到 {papers.length} 篇论文
      </div>
      {papers.map((paper, i) => {
        const dl = downloaded[paper.arxiv_id];
        return (
          <div key={paper.arxiv_id + i}>
            <InfoCard
              type="paper"
              title={paper.title}
              snippet={paper.abstract_zh}
              sourceLabel="arXiv"
              url={paper.arxiv_url}
              tags={[
                { label: String(paper.year) },
                { label: paper.citations },
                { label: `arXiv:${paper.arxiv_id}` },
              ]}
              actionLabel={dl ? '全屏阅读' : '下载阅读'}
              actionLoading={downloadingId === paper.arxiv_id}
              onAction={() => {
                if (dl) {
                  setFullReader(dl);
                } else {
                  handleDownload(paper);
                }
              }}
            />
            {dl && (
              <PaperInlineReader
                fileId={dl.fileId}
                fileName={dl.fileName}
                title={dl.title}
                messageId={message.id}
                onExpand={() => setFullReader(dl)}
              />
            )}
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
