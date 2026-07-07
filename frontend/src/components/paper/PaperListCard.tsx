/**
 * PaperListCard：论文列表卡片 + 内联阅读器。
 * 每篇论文独立下载、独立显示阅读器。
 */
import { useState } from 'react';
import { Button, MessagePlugin } from 'tdesign-react';
import { DownloadIcon } from 'tdesign-icons-react';
import type { PaperInfo, ChatMessage } from '../../types';
import { downloadPaper, savePaper } from '../../services/paperApi';
import { useAppDispatch, useAppState } from '../../store/AppContext';
import PaperInlineReader from './PaperInlineReader';
import PaperFullReader from './PaperFullReader';

interface Props {
  message: ChatMessage;
}

interface DownloadedPaper {
  fileId: string;
  title: string;
  fileName: string;
}

export default function PaperListCard({ message }: Props) {
  const dispatch = useAppDispatch();
  const { sessionId } = useAppState();
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
      // 每篇论文独立存储，不覆盖
      setDownloaded(prev => ({
        ...prev,
        [paper.arxiv_id]: {
          fileId: result.file_id,
          title: result.title,
          fileName: result.filename,
        },
      }));
      // 自动保存到「我的阅读」
      savePaper(result.file_id, result.title, result.arxiv_id, sessionId).catch(() => {});
      MessagePlugin.success('论文已下载并保存到我的阅读');
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
            {/* 论文信息卡片 */}
            <div
              className="paper-result-card"
              style={{
                background: 'var(--app-bg-2)',
                borderRadius: 10,
                padding: 12,
                marginBottom: 8,
                border: '1px solid var(--app-border)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, lineHeight: 1.4, marginBottom: 2 }}>
                    {paper.title}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--app-text-3)', marginBottom: 4 }}>
                    {paper.authors} · {paper.year} · arXiv:{paper.arxiv_id} · {paper.citations}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--app-text-2)', lineHeight: 1.5 }}>
                    {paper.abstract_zh}
                  </div>
                  <div style={{ fontSize: 10, color: '#2b5aed', fontWeight: 500, marginTop: 3 }}>
                    💡 {paper.key_contribution}
                  </div>
                </div>
                {!dl ? (
                  <Button
                    theme="primary"
                    size="small"
                    loading={downloadingId === paper.arxiv_id}
                    onClick={() => handleDownload(paper)}
                    icon={<DownloadIcon />}
                    style={{ flexShrink: 0 }}
                  >
                    下载阅读
                  </Button>
                ) : (
                  <Button
                    size="small"
                    variant="outline"
                    onClick={() => setFullReader(dl)}
                    style={{ flexShrink: 0 }}
                  >
                    全屏阅读
                  </Button>
                )}
              </div>
            </div>

            {/* 该论文的内联预览（独立，不互相覆盖） */}
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

      {/* 全屏阅读器 */}
      {fullReader && (
        <PaperFullReader
          fileId={fullReader.fileId}
          title={fullReader.title}
          onClose={() => setFullReader(null)}
        />
      )}
    </div>
  );
}
