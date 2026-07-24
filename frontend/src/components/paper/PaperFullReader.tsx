/**
 * PaperFullReader：单一高清兼容预览 + 论文助读。
 * 画面按设备像素比渲染，TextLayer 仅负责原生选词与助读菜单。
 */
import { useEffect, useRef, useState } from 'react';
import { Button, Loading, MessagePlugin, Textarea, Tag } from 'tdesign-react';
import { CloseIcon, FullscreenExitIcon, FullscreenIcon } from 'tdesign-icons-react';
import * as pdfjsLib from 'pdfjs-dist';
import { fetchPaperFile } from '../../services/paperApi';
import {
  loadPdf, extractParagraphs, isNonInteractiveParagraph,
  type PDFDocumentProxy, type Paragraph,
} from '../../services/pdf';
import {
  translateParagraph, summarizeParagraph,
  analyzePaper, paperQA, loadPaperAssistantResults, savePaperAssistantResult,
  type PaperAssistantResult,
} from '../../services/paperApi';
import MarkdownRenderer from '../common/MarkdownRenderer';
import { useLanguage } from '../../i18n';

interface Props {
  fileId: string;
  title: string;
  arxivId?: string;
  assistantEnabled?: boolean;
  onClose: () => void;
}

type AIAction = 'translate' | 'summarize' | 'analyze' | 'qa';

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

export default function PaperFullReader({ fileId, title, assistantEnabled = true, onClose }: Props) {
  const { language, t } = useLanguage();
  const locale = language === 'zh-TW' ? 'zh-TW' : language === 'en' ? 'en' : 'zh-CN';
  const readerRef = useRef<HTMLDivElement>(null);
  const canvasRefs = useRef<Map<number, HTMLCanvasElement>>(new Map());
  const textLayerRefs = useRef<Map<number, HTMLDivElement>>(new Map());

  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [pages, setPages] = useState<PageData[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [hover, setHover] = useState<{ page: number; index: number } | null>(null);
  const [active, setActive] = useState<{ page: number; index: number } | null>(null);
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number; text: string } | null>(null);
  const [floatBar, setFloatBar] = useState<{ x: number; y: number; text: string } | null>(null);
  const [scale, setScale] = useState(1.25);

  const [aiResult, setAiResult] = useState<AIResult | null>(null);
  const [aiTab, setAiTab] = useState<'result' | 'qa'>('result');
  const [qaInput, setQaInput] = useState('');
  const [qaHistory, setQaHistory] = useState<{ q: string; a: string }[]>([]);
  const [savedTranslations, setSavedTranslations] = useState<PaperAssistantResult[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const streamRef = useRef<{ cancel: () => void } | null>(null);

  useEffect(() => {
    let cancelled = false;
    setHistoryLoading(true);
    void loadPaperAssistantResults(fileId)
      .then((items) => {
        if (cancelled) return;
        const translations = items.filter((item) => item.action === 'translate');
        setSavedTranslations(translations);
      })
      .catch(() => {
        if (!cancelled) setSavedTranslations([]);
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false);
      });
    return () => { cancelled = true; };
  }, [fileId]);

  useEffect(() => {
    let cancelled = false;
    const fetchController = new AbortController();
    let fetchTimer = 0;
    renderedScaleRef.current = 0;  // 重置，让渲染 effect 重新执行
    (async () => {
      try {
        setLoading(true); setLoadError('');
        fetchTimer = window.setTimeout(() => fetchController.abort(), 30_000);
        const resp = await fetchPaperFile(fileId, fetchController.signal);
        window.clearTimeout(fetchTimer);
        if (!resp.ok) throw new Error(t('pdfDownloadStatusFailed', { status: resp.status }));
        const blob = await resp.blob();
        const buffer = await blob.arrayBuffer();
        const d = await loadPdf(buffer);
        if (cancelled) return;
        setDoc(d);
        // Mount all page canvases immediately. Paragraph extraction now runs
        // alongside progressive rendering instead of blocking the first frame.
        setPages(Array.from({ length: d.numPages }, (_, index) => ({ pageNum: index + 1, width: 0, height: 0, paragraphs: [], rendered: false })));
        setLoading(false);
      } catch (error) {
        if (!cancelled) setLoadError(error instanceof DOMException && error.name === 'AbortError' ? t('pdfDownloadTimedOut') : error instanceof Error ? error.message : t('pdfCannotOpen'));
        setLoading(false);
      }
    })();
    return () => { cancelled = true; window.clearTimeout(fetchTimer); fetchController.abort(); };
  }, [fileId, t]);

  useEffect(() => {
    const onFullscreenChange = () => setIsFullscreen(document.fullscreenElement === readerRef.current);
    document.addEventListener('fullscreenchange', onFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', onFullscreenChange);
  }, []);

  // 渲染 canvas + text layer（scale 变化时重新渲染）
  // 用 ref 跟踪已渲染的 scale，避免 setPages 导致无限循环
  const renderedScaleRef = useRef<number>(0);

  useEffect(() => {
    if (!doc || pages.length === 0) return;
    if (renderedScaleRef.current === scale) return;  // scale 没变就不渲染
    renderedScaleRef.current = scale;

    let cancelled = false;

    const renderPages = async () => {
      const enriched: PageData[] = [];
      for (const pg of pages) {
        if (cancelled) return;
        const canvas = canvasRefs.current.get(pg.pageNum);
        const textLayerDiv = textLayerRefs.current.get(pg.pageNum);
        if (!canvas) continue;

        const page = await doc.getPage(pg.pageNum);
        const viewport = page.getViewport({ scale });
        const outputScale = Math.min(2.5, Math.max(1, window.devicePixelRatio || 1));

        // 1. 渲染 canvas
        canvas.width = Math.floor(viewport.width * outputScale);
        canvas.height = Math.floor(viewport.height * outputScale);
        canvas.style.width = `${viewport.width}px`;
        canvas.style.height = `${viewport.height}px`;
        const ctx = canvas.getContext('2d');
        if (!ctx) continue;
        await page.render({
          canvasContext: ctx,
          viewport,
          transform: outputScale === 1 ? undefined : [outputScale, 0, 0, outputScale, 0, 0],
        }).promise;

        // 2. 渲染 text layer
        if (textLayerDiv) {
          textLayerDiv.innerHTML = '';
          textLayerDiv.style.width = `${viewport.width}px`;
          textLayerDiv.style.height = `${viewport.height}px`;
          try {
            const textContent = await page.getTextContent();
            const textLayer = new pdfjsLib.TextLayer({
              textContentSource: textContent,
              container: textLayerDiv,
              viewport: viewport,
            });
            await textLayer.render();
          } catch (e) {
            console.warn('TextLayer render failed for page', pg.pageNum, e);
          }
        }
        let paragraphs: Paragraph[] = [];
        try { paragraphs = await extractParagraphs(page); } catch { /* canvas remains usable */ }
        enriched.push({ ...pg, width: viewport.width / scale, height: viewport.height / scale, paragraphs, rendered: true });
      }
      if (!cancelled && enriched.length === pages.length) setPages(enriched);
    };
    void renderPages().catch((error) => {
      if (!cancelled) setLoadError(error instanceof Error ? t('pdfRenderFailed', { error: error.message }) : t('pdfPageRenderFailed'));
    });
    return () => { cancelled = true; };
  }, [doc, pages, scale, t]);

  // 段落命中检测（基于 text layer 的选择文本）
  const getSelectedText = (): string => {
    const sel = window.getSelection();
    return sel
      ? sel.toString()
        .replace(/\u00ad/g, '')
        .replace(/([\p{L}\p{N}])-\s+([\p{L}\p{N}])/gu, '$1$2')
        .replace(/\s+/g, ' ')
        .trim()
        .slice(0, 12000)
      : '';
  };

  const findParagraphByPoint = (e: React.MouseEvent, pageNum: number): Paragraph | null => {
    const canvas = canvasRefs.current.get(pageNum);
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    if (rect.width === 0) return null;
    // CSS 坐标 → PDF scale=1 坐标
    const cssX = e.clientX - rect.left;
    const cssY = e.clientY - rect.top;
    const pdfX = cssX / scale;
    const pdfY = cssY / scale;
    const pg = pages.find(p => p.pageNum === pageNum);
    if (!pg) return null;
    for (let i = pg.paragraphs.length - 1; i >= 0; i--) {
      const para = pg.paragraphs[i];
      if (isNonInteractiveParagraph(para)) continue;
      for (const r of para.rects) {
        if (pdfX >= r.x && pdfX <= r.x + r.w && pdfY >= r.y && pdfY <= r.y + r.h) return para;
      }
    }
    return null;
  };

  const handleMouseMove = (e: React.MouseEvent, pageNum: number) => {
    if (window.getSelection()?.toString()) return;
    const para = findParagraphByPoint(e, pageNum);
    setHover(para ? { page: pageNum, index: para.index } : null);
  };

  // 鼠标释放：如果选中了文字，显示浮动工具条（不自动翻译）
  const handleMouseUp = () => {
    if (!assistantEnabled) return;
    const sel = getSelectedText();
    if (sel && sel.length > 1) {
      // 稍延迟获取选区位置（等浏览器更新）
      setTimeout(() => {
        const rect = window.getSelection()?.getRangeAt(0).getBoundingClientRect();
        if (rect) {
          setFloatBar({
            x: rect.left + rect.width / 2,
            y: rect.top - 8,
            text: sel,
          });
        }
      }, 10);
    } else {
      setFloatBar(null);
    }
  };

  // 单击：关闭浮动条，不做自动翻译
  const handleClick = () => {
    setFloatBar(null);
  };

  const handleDoubleClick = (e: React.MouseEvent, pageNum: number) => {
    if (!assistantEnabled) return;
    const sel = getSelectedText();
    if (sel && sel.length > 2) {
      runAI('summarize', sel, t('summarizeSelection'));
      return;
    }
    const para = findParagraphByPoint(e, pageNum);
    if (!para) return;
    setActive({ page: pageNum, index: para.index });
    runAI('summarize', para.text, t('paragraphSummary'));
  };

  const handleContextMenu = (e: React.MouseEvent, pageNum: number) => {
    if (!assistantEnabled) return;
    e.preventDefault();
    const sel = getSelectedText();
    const para = findParagraphByPoint(e, pageNum);
    const text = sel || para?.text || '';
    if (text) {
      setCtxMenu({ x: e.clientX, y: e.clientY, text });
    }
  };

  const runAI = (action: AIAction, text: string, title: string) => {
    if (streamRef.current) streamRef.current.cancel();
    setAiResult({ action, title, content: '', streaming: true });
    setAiTab('result');
    const onDelta = (delta: string) => setAiResult(prev => prev ? { ...prev, content: prev.content + delta } : prev);
    const onDone = (full: string, error?: string) => {
      setAiResult(prev => prev ? { ...prev, content: error ? `❌ ${error}` : full, streaming: false } : prev);
      if (action === 'translate' && !error && full.trim()) {
        void savePaperAssistantResult(fileId, {
          action: 'translate',
          title,
          source_text: text,
          content: full,
        }).then((saved) => {
          setSavedTranslations((current) => [...current.filter((item) => item.id !== saved.id), saved].slice(-50));
          setAiResult(null);
        }).catch((saveError) => {
          MessagePlugin.warning(saveError instanceof Error ? saveError.message : t('translationNotSaved'));
        });
      }
    };
    const documentText = pages.map((page) => `【第 ${page.pageNum} 页】\n${page.paragraphs.map((paragraph) => paragraph.text).join('\n')}`).join('\n\n');
    switch (action) {
      case 'translate': streamRef.current = translateParagraph(text, onDelta, onDone); break;
      case 'summarize': streamRef.current = summarizeParagraph(text, onDelta, onDone); break;
      case 'analyze': streamRef.current = analyzePaper(fileId, onDelta, onDone, documentText); break;
    }
  };

  const toggleFullscreen = async () => {
    try {
      if (document.fullscreenElement === readerRef.current) await document.exitFullscreen();
      else await readerRef.current?.requestFullscreen?.();
    } catch {
      MessagePlugin.warning(t('fullscreenUnsupported'));
    }
  };

  const handleQA = () => {
    if (!qaInput.trim()) return;
    const q = qaInput.trim();
    setQaInput('');
    setAiTab('qa');
    setAiResult({ action: 'qa', title: q, content: '', streaming: true });
    const onDelta = (delta: string) => setAiResult(prev => prev ? { ...prev, content: prev.content + delta } : prev);
    const onDone = (full: string, error?: string) => {
      setAiResult(prev => prev ? { ...prev, streaming: false } : prev);
      setQaHistory(prev => [...prev, { q, a: error ? `❌ ${error}` : full }]);
      setAiResult(null);
    };
    const documentText = pages.map((page) => `【第 ${page.pageNum} 页】\n${page.paragraphs.map((paragraph) => paragraph.text).join('\n')}`).join('\n\n');
    streamRef.current = paperQA(fileId, q, onDelta, onDone, documentText);
  };

  const closeMenu = () => { setCtxMenu(null); };

  // 点击其他地方关闭浮动条
  useEffect(() => {
    if (!floatBar) return;
    const handler = () => setFloatBar(null);
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [floatBar]);
  useEffect(() => {
    if (ctxMenu) {
      document.addEventListener('click', closeMenu);
      return () => document.removeEventListener('click', closeMenu);
    }
  }, [ctxMenu]);

  return (
    <div className="paper-reader-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="paper-reader" ref={readerRef} role="dialog" aria-modal="true" aria-label={t('paperAssistantAria', { title })}>
        <div className="paper-toolbar">
          <div className="paper-toolbar-title">
            <span style={{ fontSize: 16 }}>📄</span>
            <span className="paper-toolbar-title-text">{title}</span>
            {doc && <Tag size="small" variant="light">{t('pageCount', { count: doc.numPages }).replace(/^\s*·\s*/, '')}</Tag>}
            <Tag size="small" variant="outline">{t('compatiblePreview')}</Tag>
          </div>
          <div className="paper-toolbar-actions">
            <Button
              size="small"
              variant="outline"
              icon={isFullscreen ? <FullscreenExitIcon /> : <FullscreenIcon />}
              onClick={() => void toggleFullscreen()}
            >{isFullscreen ? t('restoreWindow') : t('fullscreen')}</Button>
            <span className="paper-toolbar-divider" />
            {assistantEnabled && <Button size="small" variant="outline" onClick={() => runAI('analyze', '', t('fullPaperAnalysis'))}>📚 {t('fullPaperAnalysis')}</Button>}
            <Button size="small" variant="text" aria-label={t('zoomOut')} title={t('zoomOut')} onClick={() => setScale(s => Math.max(0.6, s - 0.3))}>−</Button>
            <span className="paper-zoom-value">{Math.round(scale * 100)}%</span>
            <Button size="small" variant="text" aria-label={t('zoomIn')} title={t('zoomIn')} onClick={() => setScale(s => Math.min(3.0, s + 0.3))}>+</Button>
            <Button shape="circle" variant="text" size="small" onClick={onClose} aria-label={t('closePaperAssistant')} title={t('closePaperAssistant')} icon={<CloseIcon />} />
          </div>
        </div>

        <div className="paper-body" style={{ display: 'flex', overflow: 'hidden' }}>
          {/* PDF 侧 */}
          <div className="paper-compatible-view">
            {loading && <div className="paper-loading-state"><Loading /><span>{t('openingHdPreview')}</span></div>}
            {loadError && <div className="paper-load-error"><strong>{t('pdfOpenFailed')}</strong><span>{loadError}</span></div>}
            {doc && pages.map(pg => (
              <div
                key={pg.pageNum}
                style={{ position: 'relative', marginBottom: 12, display: 'inline-block' }}
                onMouseMove={(e) => handleMouseMove(e, pg.pageNum)}
                onClick={handleClick}
                onDoubleClick={(e) => handleDoubleClick(e, pg.pageNum)}
                onMouseUp={handleMouseUp}
                onContextMenu={(e) => handleContextMenu(e, pg.pageNum)}
              >
                <canvas
                  ref={el => { if (el) canvasRefs.current.set(pg.pageNum, el); }}
                  style={{ display: 'block', boxShadow: '0 2px 8px rgba(0,0,0,0.2)' }}
                />
                {/* TextLayer - 原生文本选择 */}
                <div
                  ref={el => { if (el) textLayerRefs.current.set(pg.pageNum, el); }}
                  className="pdf-text-layer"
                />
                {/* 段落悬停高亮层 - pointer-events: none 不拦截选择 */}
                {pg.paragraphs.map(para => {
                  if (isNonInteractiveParagraph(para)) return null;
                  const isHover = hover?.page === pg.pageNum && hover.index === para.index;
                  const isActive = active?.page === pg.pageNum && active.index === para.index;
                  // 段落坐标在 scale=1 下，需要乘以当前 scale
                  return (
                    <div
                      key={para.index}
                      style={{
                        position: 'absolute',
                        left: para.bbox.x * scale,
                        top: para.bbox.y * scale,
                        width: para.bbox.w * scale,
                        height: para.bbox.h * scale,
                        background: isActive ? 'rgba(43,90,237,0.08)' : isHover ? 'rgba(43,90,237,0.05)' : 'transparent',
                        border: isActive ? '1px solid rgba(43,90,237,0.3)' : 'none',
                        borderRadius: 2,
                        pointerEvents: 'none',
                        zIndex: 5,
                      }}
                    />
                  );
                })}
                <div style={{ textAlign: 'center', fontSize: 10, color: 'rgba(255,255,255,0.4)', padding: '2px 0' }}>— {pg.pageNum} —</div>
              </div>
            ))}
          </div>

          {/* AI 侧 - 自适应宽度 */}
          {assistantEnabled && <div className="paper-ai-side">
            <div className="paper-ai-tabs">
              <button className={`paper-ai-tab ${aiTab === 'result' ? 'active' : ''}`} onClick={() => setAiTab('result')}>📑 {t('results')}</button>
              <button className={`paper-ai-tab ${aiTab === 'qa' ? 'active' : ''}`} onClick={() => setAiTab('qa')}>💬 {t('qa')}</button>
            </div>

            {aiTab === 'result' && (
              <div className="paper-ai-content">
                {!aiResult && !historyLoading && (
                  <div className="paper-ai-empty">
                    {t('paperAssistantInstructions')}<br />
                    · {t('selectTextAction')}<br />
                    · {t('doubleClickAction')}<br />
                    · {t('rightClickAction')}<br /><br />
                    {t('useFullPaperFeature')}
                  </div>
                )}
                {aiResult && (
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 6, color: '#2b5aed' }}>
                      {aiResult.title}{aiResult.streaming && <Loading size="small" style={{ marginLeft: 6 }} />}
                    </div>
                    <div className="paper-ai-result">
                      <MarkdownRenderer content={aiResult.content || '...'} />
                    </div>
                  </div>
                )}
                {savedTranslations.length > 0 && (
                  <div className="paper-translation-history">
                    <div className="paper-translation-history-title">{t('savedTranslationsCount', { count: savedTranslations.length })}</div>
                    {savedTranslations.map((item) => (
                      <article className="paper-translation-entry" key={item.id}>
                        <div className="paper-translation-time">{new Date(item.created_at).toLocaleString(locale)}</div>
                        <div className="paper-translation-entry-title">{item.title}</div>
                        <MarkdownRenderer content={item.content} />
                      </article>
                    ))}
                  </div>
                )}
              </div>
            )}

            {aiTab === 'qa' && (
              <div className="paper-ai-content" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
                <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
                  {qaHistory.length === 0 && <div style={{ textAlign: 'center', color: 'var(--app-text-3)', fontSize: 12, paddingTop: 30 }}>{t('askAboutPaper')}</div>}
                  {qaHistory.map((item, i) => (
                    <div key={i} style={{ marginBottom: 12 }}>
                      <div style={{ fontSize: 11, color: '#2b5aed', fontWeight: 600, marginBottom: 3 }}>{t('paperQuestionPrefix')} {item.q}</div>
                      <div style={{ fontSize: 12, lineHeight: 1.6 }}><MarkdownRenderer content={item.a} /></div>
                    </div>
                  ))}
                  {aiResult?.action === 'qa' && (
                    <div style={{ marginBottom: 12 }}>
                      <div style={{ fontSize: 11, color: '#2b5aed', fontWeight: 600, marginBottom: 3 }}>{t('paperQuestionPrefix')} {aiResult.title}</div>
                      <div style={{ fontSize: 12, lineHeight: 1.6 }}><MarkdownRenderer content={aiResult.content || '...'} /></div>
                    </div>
                  )}
                </div>
                <div className="paper-qa-input">
                  <Textarea value={qaInput} onChange={(v) => setQaInput(v as string)} placeholder={t('askPlaceholder')} autosize={{ minRows: 1, maxRows: 3 }} style={{ flex: 1 }}
                    onKeydown={(_, ctx) => { const e = ctx.e as React.KeyboardEvent; if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleQA(); } }} />
                  <Button theme="primary" size="small" onClick={handleQA} disabled={!qaInput.trim()}>{t('send')}</Button>
                </div>
              </div>
            )}
          </div>}
        </div>

        {/* 浮动工具条：选中文本后出现 */}
        {floatBar && (
          <div
            style={{
              position: 'fixed',
              left: floatBar.x,
              top: floatBar.y,
              transform: 'translate(-50%, -100%)',
              background: '#1a1a2e',
              borderRadius: 8,
              boxShadow: '0 4px 16px rgba(0,0,0,0.3)',
              zIndex: 10000,
              display: 'flex',
              gap: 0,
              overflow: 'hidden',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {[
              { label: t('translateWithIcon'), action: 'translate' as AIAction, title: t('translateSelection') },
              { label: t('summarizeWithIcon'), action: 'summarize' as AIAction, title: t('summarizeSelection') },
            ].map((btn, i, buttons) => (
              <button
                key={i}
                style={{
                  padding: '6px 12px',
                  border: 'none',
                  background: 'none',
                  cursor: 'pointer',
                  fontSize: 12,
                  color: '#fff',
                  borderRight: i < buttons.length - 1 ? '1px solid rgba(255,255,255,0.1)' : 'none',
                  whiteSpace: 'nowrap',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.15)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'none')}
                onClick={() => {
                  runAI(btn.action, floatBar.text, btn.title);
                  setFloatBar(null);
                  window.getSelection()?.removeAllRanges();
                }}
              >
                {btn.label}
              </button>
            ))}
          </div>
        )}

        {ctxMenu && (
          <div style={{
            position: 'fixed', left: ctxMenu.x, top: ctxMenu.y,
            background: '#ffffff', border: '1px solid #d0d0d0',
            borderRadius: 8, boxShadow: '0 4px 16px rgba(0,0,0,0.25)', zIndex: 10001,
            padding: 4, minWidth: 150,
          }} onClick={(e) => e.stopPropagation()}>
            {[
              { label: t('translateWithIcon'), action: 'translate' as AIAction },
              { label: t('summarizeWithIcon'), action: 'summarize' as AIAction },
            ].map(item => (
              <button key={item.action} className="ctx-menu-item"
                style={{ display: 'block', width: '100%', padding: '6px 10px', border: 'none', background: 'none', cursor: 'pointer', fontSize: 12, textAlign: 'left', borderRadius: 4, color: '#333' }}
                onMouseEnter={(e) => (e.currentTarget.style.background = '#f0f4ff')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'none')}
                onClick={() => {
                  const titles: Record<string, string> = { translate: t('translate'), summarize: t('summarize') };
                  runAI(item.action, ctxMenu.text, titles[item.action]);
                  setCtxMenu(null);
                }}
              >{item.label}</button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
