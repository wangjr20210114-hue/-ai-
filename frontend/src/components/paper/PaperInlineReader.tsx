/**
 * PaperInlineReader：内联在对话中的论文预览。
 * 极简：只渲染 PDF（高清晰度）+ 全屏按钮。
 */
import { useEffect, useRef, useState } from 'react';
import { Button, Loading, MessagePlugin } from 'tdesign-react';
import { FullscreenIcon } from 'tdesign-icons-react';
import { loadPdf, type PDFDocumentProxy } from '../../services/pdf';

interface Props {
  fileId: string;
  fileName: string;
  title: string;
  messageId: string;
  onExpand?: () => void;
}

interface PageData {
  pageNum: number;
  width: number;
  height: number;
  rendered: boolean;
}

export default function PaperInlineReader({ fileId, fileName, title, onExpand }: Props) {
  const canvasRefs = useRef<Map<number, HTMLCanvasElement>>(new Map());
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [pages, setPages] = useState<PageData[]>([]);
  const [loading, setLoading] = useState(true);
  // 高清渲染：用 2x scale 渲染，CSS 缩小显示
  const renderScale = 1.5;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await fetch(`/api/paper/file/${fileId}`);
        if (!resp.ok) { MessagePlugin.error('加载 PDF 失败'); setLoading(false); return; }
        const blob = await resp.blob();
        const buffer = await blob.arrayBuffer();
        const d = await loadPdf(buffer);
        if (cancelled) return;
        setDoc(d);
        const newPages: PageData[] = [];
        for (let i = 1; i <= d.numPages; i++) {
          const p = await d.getPage(i);
          const vp = p.getViewport({ scale: 1 });
          newPages.push({ pageNum: i, width: vp.width, height: vp.height, rendered: false });
        }
        if (cancelled) return;
        setPages(newPages);
        setLoading(false);
      } catch {
        MessagePlugin.error('加载 PDF 失败');
        setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [fileId]);

  useEffect(() => {
    if (!doc || pages.length === 0) return;
    let cancelled = false;
    const renderPages = async () => {
      for (const pg of pages) {
        if (cancelled || pg.rendered) continue;
        const canvas = canvasRefs.current.get(pg.pageNum);
        if (!canvas) continue;
        const page = await doc.getPage(pg.pageNum);
        const viewport = page.getViewport({ scale: renderScale });
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
  }, [doc, pages]);

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 100 }}>
        <Loading text="正在加载论文..." />
      </div>
    );
  }

  return (
    <div style={{
      marginTop: 10,
      border: '1px solid var(--app-border)',
      borderRadius: 10,
      overflow: 'hidden',
      background: '#525659',
    }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '6px 10px', background: 'var(--app-bg-2)',
      }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--app-text)' }}>
          📄 {title || fileName}
        </span>
        {onExpand && (
          <Button size="small" variant="outline" onClick={onExpand} icon={<FullscreenIcon />}>
            全屏阅读
          </Button>
        )}
      </div>
      <div style={{ maxHeight: 400, overflowY: 'auto', padding: 8 }}>
        {doc && pages.map(pg => (
          <div key={pg.pageNum} style={{ marginBottom: 4 }}>
            <canvas
              ref={el => { if (el) canvasRefs.current.set(pg.pageNum, el); }}
              style={{ display: 'block', width: '100%', boxShadow: '0 2px 6px rgba(0,0,0,0.3)' }}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
