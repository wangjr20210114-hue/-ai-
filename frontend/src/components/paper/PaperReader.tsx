import { authorizedFetch } from '../../services/auth';
/**
 * PaperReader：全屏论文阅读器。
 * 流程：搜索论文 → 展示推荐列表 → 用户选一篇 → 自动下载 PDF → 打开阅读器
 * 阅读器：段落提取 + 悬停高亮 + 单击翻译 + 双击总结 + 右键菜单 + 全文分析/翻译/术语 + QA
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import { Button, Loading, MessagePlugin, Textarea } from 'tdesign-react';
import { CloseIcon, SearchIcon, DownloadIcon, ArrowLeftIcon } from 'tdesign-icons-react';
import {
  loadPdf, extractParagraphs, isNonInteractiveParagraph,
  type PDFDocumentProxy, type Paragraph,
} from '../../services/pdf';
import {
  searchPapers, downloadPaper,
  translateParagraph, summarizeParagraph,
  explainTerm, explainFormula, analyzePaper, fullTranslate, extractTerms, paperQA,
  type PaperInfo,
} from '../../services/paperApi';
import MarkdownRenderer from '../common/MarkdownRenderer';

interface Props {
  onClose: () => void;
  initialTopic?: string;
}

type AIAction = 'translate' | 'summarize' | 'explain' | 'formula' | 'analyze' | 'full-translate' | 'terms' | 'qa';
type Phase = 'search' | 'results' | 'reading';

interface AIResult {
  action: AIAction;
  title: string;
  content: string;
  streaming: boolean;
}

interface PageData {
  pageNum: number;
  width: number;
  height: number;
  paragraphs: Paragraph[];
  rendered: boolean;
}

export default function PaperReader({ onClose, initialTopic }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRefs = useRef<Map<number, HTMLCanvasElement>>(new Map());

  // 阶段控制
  const [phase, setPhase] = useState<Phase>(initialTopic ? 'results' : 'search');
  const [searchTopic, setSearchTopic] = useState(initialTopic || '');
  const [searching, setSearching] = useState(false);
  const [papers, setPapers] = useState<PaperInfo[]>([]);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  // PDF 状态
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [pages, setPages] = useState<PageData[]>([]);
  const [hover, setHover] = useState<{ page: number; index: number } | null>(null);
  const [active, setActive] = useState<{ page: number; index: number } | null>(null);
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number; para: Paragraph } | null>(null);
  const [fileId, setFileId] = useState<string>('');
  const [fileName, setFileName] = useState<string>('');
  const [paperTitle, setPaperTitle] = useState<string>('');
  const [scale] = useState(1.2);

  // AI 状态
  const [aiResult, setAiResult] = useState<AIResult | null>(null);
  const [aiTab, setAiTab] = useState<'result' | 'qa'>('result');
  const [qaInput, setQaInput] = useState('');
  const [qaHistory, setQaHistory] = useState<{ q: string; a: string }[]>([]);
  const streamRef = useRef<{ cancel: () => void } | null>(null);

  // === 搜索 ===
  const handleSearch = useCallback(async (topic?: string) => {
    const t = (topic || searchTopic).trim();
    if (!t) return;
    setSearching(true);
    setPapers([]);
    try {
      const result = await searchPapers(t);
      if (result.error) {
        MessagePlugin.warning(result.error);
      } else if (result.papers.length === 0) {
        MessagePlugin.info('未找到相关论文');
      } else {
        setPapers(result.papers);
        setPhase('results');
      }
    } catch {
      MessagePlugin.error('搜索失败');
    } finally {
      setSearching(false);
    }
  }, [searchTopic]);

  // 自动搜索（如果传入了 initialTopic，直接开始搜索）
  useEffect(() => {
    if (initialTopic) {
      setSearchTopic(initialTopic);
      setSearching(true);
      searchPapers(initialTopic).then(result => {
        setSearching(false);
        if (result.error) {
          MessagePlugin.warning(result.error);
        } else if (result.papers.length === 0) {
          MessagePlugin.info('未找到相关论文');
        } else {
          setPapers(result.papers);
        }
      }).catch(() => {
        setSearching(false);
        MessagePlugin.error('搜索失败');
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // === 下载论文 ===
  const handleDownload = async (paper: PaperInfo) => {
    setDownloadingId(paper.arxiv_id);
    MessagePlugin.info(`正在下载 ${paper.title.slice(0, 40)}...`);
    try {
      const result = await downloadPaper(paper.arxiv_id, paper.title);
      if (result.error) {
        MessagePlugin.warning(result.error);
        setDownloadingId(null);
        return;
      }

      // 下载成功，加载 PDF
      setFileId(result.file_id);
      setFileName(result.filename);
      setPaperTitle(result.title);

      // 从后端获取 PDF 文件内容
      const fileResp = await authorizedFetch(`/api/paper/file/${result.file_id}`);
      if (fileResp.ok) {
        const blob = await fileResp.blob();
        const buffer = await blob.arrayBuffer();
        const d = await loadPdf(buffer);
        setDoc(d);

        const newPages: PageData[] = [];
        for (let i = 1; i <= d.numPages; i++) {
          const p = await d.getPage(i);
          const vp = p.getViewport({ scale: 1 });
          const paras = await extractParagraphs(p);
          newPages.push({ pageNum: i, width: vp.width, height: vp.height, paragraphs: paras, rendered: false });
        }
        setPages(newPages);
        setPhase('reading');
        MessagePlugin.success(`已加载 ${d.numPages} 页论文`);
      } else {
        MessagePlugin.error('PDF 下载成功但无法加载预览');
        setDownloadingId(null);
      }
    } catch {
      MessagePlugin.error('下载失败');
    } finally {
      setDownloadingId(null);
    }
  };

  // 渲染 canvas
  useEffect(() => {
    if (!doc || pages.length === 0) return;
    let cancelled = false;
    const renderPages = async () => {
      for (const pg of pages) {
        if (cancelled || pg.rendered) continue;
        const canvas = canvasRefs.current.get(pg.pageNum);
        if (!canvas) continue;
        const page = await doc.getPage(pg.pageNum);
        const viewport = page.getViewport({ scale });
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        const ctx = canvas.getContext('2d');
        if (!ctx) continue;
        await page.render({ canvasContext: ctx, viewport }).promise;
        if (!cancelled) pg.rendered = true;
      }
    };
    renderPages();
    return () => { cancelled = true; };
  }, [doc, pages, scale]);

  // 段落命中
  const findParagraph = (e: React.MouseEvent, pageNum: number): Paragraph | null => {
    const canvas = canvasRefs.current.get(pageNum);
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const x = (e.clientX - rect.left) / scale;
    const y = (e.clientY - rect.top) / scale;
    const pg = pages.find(p => p.pageNum === pageNum);
    if (!pg) return null;
    for (let i = pg.paragraphs.length - 1; i >= 0; i--) {
      const para = pg.paragraphs[i];
      if (isNonInteractiveParagraph(para)) continue;
      if (x >= para.bbox.x && x <= para.bbox.x + para.bbox.w &&
          y >= para.bbox.y && y <= para.bbox.y + para.bbox.h) {
        return para;
      }
    }
    return null;
  };

  const handleMouseMove = (e: React.MouseEvent, pageNum: number) => {
    const para = findParagraph(e, pageNum);
    setHover(para ? { page: pageNum, index: para.index } : null);
  };

  const handleClick = (e: React.MouseEvent, pageNum: number) => {
    const para = findParagraph(e, pageNum);
    if (!para) return;
    setActive({ page: pageNum, index: para.index });
    runAI('translate', para.text, '翻译段落');
  };

  const handleDoubleClick = (e: React.MouseEvent, pageNum: number) => {
    const para = findParagraph(e, pageNum);
    if (!para) return;
    setActive({ page: pageNum, index: para.index });
    runAI('summarize', para.text, '段落总结');
  };

  const handleContextMenu = (e: React.MouseEvent, pageNum: number) => {
    e.preventDefault();
    const para = findParagraph(e, pageNum);
    if (!para) return;
    setCtxMenu({ x: e.clientX, y: e.clientY, para });
  };

  // AI 执行
  const runAI = (action: AIAction, text: string, title: string) => {
    if (streamRef.current) streamRef.current.cancel();
    setAiResult({ action, title, content: '', streaming: true });
    setAiTab('result');
    const onDelta = (delta: string) => {
      setAiResult(prev => prev ? { ...prev, content: prev.content + delta } : prev);
    };
    const onDone = (full: string, error?: string) => {
      setAiResult(prev => prev ? { ...prev, content: error ? `❌ ${error}` : full, streaming: false } : prev);
    };
    switch (action) {
      case 'translate': streamRef.current = translateParagraph(text, onDelta, onDone); break;
      case 'summarize': streamRef.current = summarizeParagraph(text, onDelta, onDone); break;
      case 'explain': streamRef.current = explainTerm(text, onDelta, onDone); break;
      case 'formula': streamRef.current = explainFormula(text, onDelta, onDone); break;
      case 'analyze': streamRef.current = analyzePaper(fileId, onDelta, onDone); break;
      case 'full-translate': streamRef.current = fullTranslate(fileId, onDelta, onDone); break;
      case 'terms': streamRef.current = extractTerms(fileId, onDelta, onDone); break;
    }
  };

  const handleQA = () => {
    if (!qaInput.trim() || !fileId) return;
    const q = qaInput.trim();
    setQaInput('');
    setAiTab('qa');
    setAiResult({ action: 'qa', title: q, content: '', streaming: true });
    const onDelta = (delta: string) => {
      setAiResult(prev => prev ? { ...prev, content: prev.content + delta } : prev);
    };
    const onDone = (full: string, error?: string) => {
      setAiResult(prev => prev ? { ...prev, streaming: false } : prev);
      setQaHistory(prev => [...prev, { q, a: error ? `❌ ${error}` : full }]);
      setAiResult(null);
    };
    streamRef.current = paperQA(fileId, q, onDelta, onDone);
  };

  const closeMenu = () => setCtxMenu(null);
  useEffect(() => {
    if (ctxMenu) {
      document.addEventListener('click', closeMenu);
      return () => document.removeEventListener('click', closeMenu);
    }
  }, [ctxMenu]);

  return (
    <div className="paper-reader-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="paper-reader">
        {/* 顶部工具栏 */}
        <div className="paper-toolbar">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {phase === 'reading' && (
              <Button
                shape="circle"
                variant="text"
                size="small"
                onClick={() => setPhase('results')}
                icon={<ArrowLeftIcon />}
              />
            )}
            <span style={{ fontSize: 18 }}>📄</span>
            <span style={{ fontWeight: 600, fontSize: 14 }}>
              {phase === 'search' ? '搜索论文' : phase === 'results' ? `「${searchTopic}」的推荐论文` : (paperTitle || fileName || '论文阅读')}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {phase === 'reading' && fileId && (
              <>
                <Button size="small" variant="outline" onClick={() => runAI('analyze', '', '全文分析')}>
                  📚 全文分析
                </Button>
                <Button size="small" variant="outline" onClick={() => runAI('full-translate', '', '全文翻译')}>
                  🌍 全文翻译
                </Button>
                <Button size="small" variant="outline" onClick={() => runAI('terms', '', '术语提取')}>
                  🔑 术语
                </Button>
              </>
            )}
            <Button shape="circle" variant="text" size="small" onClick={onClose} icon={<CloseIcon />} />
          </div>
        </div>

        <div className="paper-body">
          {/* === 搜索阶段 === */}
          {phase === 'search' && (
            <div className="paper-search-zone">
              <div style={{ fontSize: 48, marginBottom: 16 }}>📄</div>
              <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 8 }}>搜索论文</div>
              <div style={{ fontSize: 13, color: 'var(--app-text-3)', marginBottom: 20, textAlign: 'center' }}>
                告诉我你想了解的领域或主题，我帮你找相关论文
              </div>
              <div style={{ display: 'flex', gap: 8, width: 400 }}>
                <input
                  type="text"
                  className="form-input-simple"
                  placeholder="如：Transformer, GPT, 多模态..."
                  value={searchTopic}
                  onChange={(e) => setSearchTopic(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleSearch(); }}
                  style={{ flex: 1 }}
                  autoFocus
                />
                <Button
                  theme="primary"
                  onClick={() => handleSearch()}
                  loading={searching}
                  icon={<SearchIcon />}
                >
                  搜索
                </Button>
              </div>
            </div>
          )}

          {/* === 结果阶段 === */}
          {phase === 'results' && (
            <div style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
              {searching && (
                <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 40 }}>
                  <Loading text="正在搜索论文..." />
                </div>
              )}
              {!searching && papers.map((paper, i) => (
                <div
                  key={paper.arxiv_id + i}
                  className="paper-result-card"
                  style={{
                    background: 'var(--app-bg-2)',
                    borderRadius: 10,
                    padding: 16,
                    marginBottom: 12,
                    border: '1px solid var(--app-border)',
                    cursor: 'pointer',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 15, fontWeight: 600, lineHeight: 1.4, marginBottom: 4 }}>
                        {paper.title}
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--app-text-3)', marginBottom: 8 }}>
                        {paper.authors} · {paper.year} · arXiv:{paper.arxiv_id} · {paper.citations}
                      </div>
                      <div style={{ fontSize: 13, color: 'var(--app-text-2)', lineHeight: 1.6, marginBottom: 8 }}>
                        {paper.abstract_zh}
                      </div>
                      <div style={{ fontSize: 12, color: '#2b5aed', fontWeight: 500 }}>
                        💡 {paper.key_contribution}
                      </div>
                    </div>
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
                  </div>
                  <a
                    href={paper.arxiv_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ fontSize: 12, color: 'var(--app-text-3)' }}
                  >
                    {paper.arxiv_url}
                  </a>
                </div>
              ))}
            </div>
          )}

          {/* === 阅读阶段 === */}
          {phase === 'reading' && (
            <>
              {/* 左侧 PDF */}
              <div className="paper-pdf-side" ref={containerRef}>
                {doc && pages.map(pg => (
                  <div key={pg.pageNum} style={{ position: 'relative', marginBottom: 12 }}>
                    <canvas
                      ref={el => { if (el) canvasRefs.current.set(pg.pageNum, el); }}
                      style={{ display: 'block', boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}
                    />
                    {pg.paragraphs.map(para => {
                      if (isNonInteractiveParagraph(para)) return null;
                      const isHover = hover?.page === pg.pageNum && hover.index === para.index;
                      const isActive = active?.page === pg.pageNum && active.index === para.index;
                      return (
                        <div
                          key={para.index}
                          style={{
                            position: 'absolute',
                            left: para.bbox.x * scale,
                            top: para.bbox.y * scale,
                            width: para.bbox.w * scale,
                            height: para.bbox.h * scale,
                            background: isActive ? 'rgba(43,90,237,0.15)' : isHover ? 'rgba(43,90,237,0.08)' : 'transparent',
                            border: isActive ? '1.5px solid rgba(43,90,237,0.5)' : isHover ? '1px solid rgba(43,90,237,0.3)' : 'none',
                            borderRadius: 2,
                            cursor: 'pointer',
                            transition: 'background 0.1s',
                          }}
                          onMouseMove={(e) => handleMouseMove(e, pg.pageNum)}
                          onClick={(e) => handleClick(e, pg.pageNum)}
                          onDoubleClick={(e) => handleDoubleClick(e, pg.pageNum)}
                          onContextMenu={(e) => handleContextMenu(e, pg.pageNum)}
                        />
                      );
                    })}
                    <div style={{ textAlign: 'center', fontSize: 11, color: 'rgba(255,255,255,0.5)', padding: '4px 0' }}>
                      — {pg.pageNum} —
                    </div>
                  </div>
                ))}
                {!doc && (
                  <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
                    <Loading text="正在加载 PDF..." />
                  </div>
                )}
              </div>

              {/* 右侧 AI 面板 */}
              <div className="paper-ai-side">
                <div className="paper-ai-tabs">
                  <button className={`paper-ai-tab ${aiTab === 'result' ? 'active' : ''}`} onClick={() => setAiTab('result')}>
                    📑 结果
                  </button>
                  <button className={`paper-ai-tab ${aiTab === 'qa' ? 'active' : ''}`} onClick={() => setAiTab('qa')}>
                    💬 问答
                  </button>
                </div>

                {aiTab === 'result' && (
                  <div className="paper-ai-content">
                    {!aiResult && (
                      <div style={{ textAlign: 'center', color: 'var(--app-text-3)', fontSize: 13, paddingTop: 40 }}>
                        在左侧 PDF 上：
                        <br /><br />
                        · <strong>单击</strong>段落 → 翻译<br />
                        · <strong>双击</strong>段落 → 总结<br />
                        · <strong>右键</strong> → 解释术语/公式<br /><br />
                        或点击顶部按钮使用全文功能
                      </div>
                    )}
                    {aiResult && (
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8, color: '#2b5aed' }}>
                          {aiResult.title}
                          {aiResult.streaming && <Loading size="small" style={{ marginLeft: 8 }} />}
                        </div>
                        <div style={{ fontSize: 13, lineHeight: 1.7, overflowY: 'auto', maxHeight: 'calc(100vh - 200px)' }}>
                          <MarkdownRenderer content={aiResult.content || '...'} />
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {aiTab === 'qa' && (
                  <div className="paper-ai-content" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
                    <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
                      {qaHistory.length === 0 && (
                        <div style={{ textAlign: 'center', color: 'var(--app-text-3)', fontSize: 13, paddingTop: 40 }}>
                          基于这篇论文向 AI 提问
                        </div>
                      )}
                      {qaHistory.map((item, i) => (
                        <div key={i} style={{ marginBottom: 16 }}>
                          <div style={{ fontSize: 12, color: '#2b5aed', fontWeight: 600, marginBottom: 4 }}>Q: {item.q}</div>
                          <div style={{ fontSize: 13, lineHeight: 1.7 }}>
                            <MarkdownRenderer content={item.a} />
                          </div>
                        </div>
                      ))}
                      {aiResult?.action === 'qa' && (
                        <div style={{ marginBottom: 16 }}>
                          <div style={{ fontSize: 12, color: '#2b5aed', fontWeight: 600, marginBottom: 4 }}>Q: {aiResult.title}</div>
                          <div style={{ fontSize: 13, lineHeight: 1.7 }}>
                            <MarkdownRenderer content={aiResult.content || '...'} />
                          </div>
                        </div>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: 8, paddingBottom: 8 }}>
                      <Textarea
                        value={qaInput}
                        onChange={(v) => setQaInput(v as string)}
                        placeholder="基于论文提问..."
                        autosize={{ minRows: 1, maxRows: 3 }}
                        style={{ flex: 1 }}
                        onKeydown={(_, ctx) => {
                          const e = ctx.e as React.KeyboardEvent;
                          if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleQA(); }
                        }}
                      />
                      <Button theme="primary" size="small" onClick={handleQA} disabled={!qaInput.trim() || !fileId}>
                        发送
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* 右键菜单 */}
        {ctxMenu && (
          <div
            style={{
              position: 'fixed', left: ctxMenu.x, top: ctxMenu.y,
              background: 'var(--app-bg-2)', border: '1px solid var(--app-border)',
              borderRadius: 8, boxShadow: '0 4px 16px rgba(0,0,0,0.15)', zIndex: 9999,
              padding: 4, minWidth: 160,
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {[
              { label: '🌐 翻译段落', action: 'translate' as AIAction },
              { label: '📝 总结段落', action: 'summarize' as AIAction },
              { label: '💡 解释术语', action: 'explain' as AIAction },
              { label: '🧮 解释公式', action: 'formula' as AIAction },
            ].map(item => (
              <button
                key={item.action}
                className="ctx-menu-item"
                style={{
                  display: 'block', width: '100%', padding: '8px 12px',
                  border: 'none', background: 'none', cursor: 'pointer',
                  fontSize: 13, textAlign: 'left', borderRadius: 4,
                  color: 'var(--app-text)',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--app-bg)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'none')}
                onClick={() => {
                  const titles: Record<string, string> = {
                    translate: '翻译段落', summarize: '段落总结',
                    explain: '解释术语', formula: '解释公式',
                  };
                  runAI(item.action, ctxMenu.para.text, titles[item.action]);
                  setCtxMenu(null);
                }}
              >
                {item.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
