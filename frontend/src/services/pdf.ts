/**
 * PDF 段落提取服务（从 paper-reader-ai 移植）。
 * 核心：extractParagraphs + detectColumns + detectFormula
 */
import * as pdfjsLib from 'pdfjs-dist';
import PdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?worker';

// EdgeOne static hosting does not serve Vite's emitted `.mjs` worker URL.
// Let Vite create a regular worker chunk and pass the Worker instance to
// PDF.js, avoiding both the 404 and preview-token propagation problems.
pdfjsLib.GlobalWorkerOptions.workerPort = new PdfWorker();

export type PDFDocumentProxy = pdfjsLib.PDFDocumentProxy;
export type PDFPageProxy = pdfjsLib.PDFPageProxy;

export interface TextItem {
  str: string;
  x: number;
  y: number;
  width: number;
  height: number;
  fontSize: number;
}

export interface Paragraph {
  page: number;
  index: number;
  text: string;
  rects: { x: number; y: number; w: number; h: number }[];
  bbox: { x: number; y: number; w: number; h: number };
  fontSize: number;
  isFormula: boolean;
}

export async function loadPdf(data: ArrayBuffer): Promise<PDFDocumentProxy> {
  const loadingTask = pdfjsLib.getDocument({ data: new Uint8Array(data) });
  let timer = 0;
  try {
    return await Promise.race([
      loadingTask.promise,
      new Promise<never>((_, reject) => {
        timer = window.setTimeout(() => {
          void loadingTask.destroy();
          reject(new Error('PDF 解析超时，请检查 PDF worker 或文件完整性'));
        }, 30_000);
      }),
    ]);
  } finally {
    window.clearTimeout(timer);
  }
}

export async function extractParagraphs(page: PDFPageProxy): Promise<Paragraph[]> {
  const viewport = page.getViewport({ scale: 1 });
  const textContent = await page.getTextContent();
  const items: TextItem[] = [];

  for (const it of textContent.items) {
    if (!('str' in it)) continue;
    if (!it.str) continue;
    const tr = it.transform as number[];
    const m = pdfjsLib.Util.transform(viewport.transform, tr);
    const baselineX = m[4];
    const baselineY = m[5];
    const w = it.width ?? 0;
    const glyphH = it.height || Math.hypot(m[2], m[3]) || 12;
    const top = baselineY - glyphH * 0.8;
    items.push({ str: it.str, x: baselineX, y: top, width: w, height: glyphH, fontSize: glyphH });
  }

  items.sort((a, b) => (a.y - b.y) || (a.x - b.x));
  const columns = detectColumns(items, viewport.width);

  let columnItems: TextItem[][];
  if (columns.length > 1) {
    const gapLeft = columns[0].right;
    const gapRight = columns[1].left;
    const colWidth = columns[0].right - columns[0].left;
    const spanItems: TextItem[] = [];
    const normalItems: TextItem[] = [];
    for (const it of items) {
      const itLeft = it.x;
      const itRight = it.x + it.width;
      const spansGap = itLeft < gapLeft && itRight > gapRight;
      const isWide = it.width > colWidth * 0.6;
      if (spansGap && isWide) spanItems.push(it);
      else normalItems.push(it);
    }
    columnItems = columns.map(col => normalItems.filter(it => {
      const center = it.x + it.width / 2;
      return center >= col.left && center <= col.right;
    }));
    if (spanItems.length > 0) columnItems.unshift(spanItems);
  } else {
    columnItems = [items];
  }

  interface Line { y: number; minX: number; maxX: number; height: number; items: TextItem[]; text: string; }
  const paragraphs: Paragraph[] = [];
  let pageIdx = 0;

  for (const colItems of columnItems) {
    if (colItems.length === 0) continue;
    colItems.sort((a, b) => (a.y - b.y) || (a.x - b.x));

    const lines: Line[] = [];
    for (const it of colItems) {
      const last = lines[lines.length - 1];
      const tol = Math.max(2, Math.min(it.height, last?.height ?? it.height) * 0.6);
      if (last && Math.abs(it.y - last.y) < tol) {
        last.items.push(it);
        last.minX = Math.min(last.minX, it.x);
        last.maxX = Math.max(last.maxX, it.x + it.width);
        last.height = (last.height + it.height) / 2;
        last.y = Math.min(last.y, it.y);
      } else {
        lines.push({ y: it.y, minX: it.x, maxX: it.x + it.width, height: it.height, items: [it], text: '' });
      }
    }

    for (const ln of lines) {
      ln.items.sort((a, b) => a.x - b.x);
      let s = '';
      let lastEnd = -1;
      for (const it of ln.items) {
        if (lastEnd >= 0 && it.x - lastEnd > it.height * 0.25 && !s.endsWith(' ') && !it.str.startsWith(' ')) s += ' ';
        s += it.str;
        lastEnd = it.x + it.width;
      }
      ln.text = s.replace(/\s+/g, ' ').trim();
    }

    let current: Line[] = [];
    const flush = () => {
      if (!current.length) return;
      // 收紧 rect：用每行实际文字范围，减少边缘空白
      const rects = current.map(l => {
        return { x: l.minX, y: l.y, w: l.maxX - l.minX, h: l.height };
      });
      // 收紧整体 bbox：去掉行首/行尾的多余空白
      const nonEmptyRects = rects.filter(r => r.w > 0 && r.h > 0);
      if (nonEmptyRects.length === 0) { current = []; return; }
      const minX = Math.min(...nonEmptyRects.map(r => r.x));
      const minY = Math.min(...nonEmptyRects.map(r => r.y));
      const maxX = Math.max(...nonEmptyRects.map(r => r.x + r.w));
      const maxY = Math.max(...nonEmptyRects.map(r => r.y + r.h));
      let txt = current.map(l => l.text).join(' ').replace(/\s+/g, ' ').trim();
      txt = txt.replace(/(\w)-\s+(\w)/g, '$1$2');
      if (txt.length > 0) {
        const heights = current.map(l => l.height).sort((a, b) => a - b);
        const fontSize = heights[Math.floor(heights.length / 2)] || 12;
        paragraphs.push({
          page: page.pageNumber, index: pageIdx++, text: txt, rects,
          bbox: { x: minX, y: minY, w: maxX - minX, h: maxY - minY },
          fontSize, isFormula: detectFormula(txt),
        });
      }
      current = [];
    };

    for (let i = 0; i < lines.length; i++) {
      const ln = lines[i];
      if (!ln.text) continue;
      const prev = current[current.length - 1];
      if (!prev) { current.push(ln); continue; }
      const gap = ln.y - (prev.y + prev.height);
      const indent = ln.minX - prev.minX;
      const gapThreshold = ln.height * 0.7;
      if (gap > gapThreshold || indent > ln.height * 1.2) flush();
      current.push(ln);
    }
    flush();
  }
  return paragraphs;
}

function detectColumns(items: TextItem[], pageWidth: number): { left: number; right: number }[] {
  if (items.length < 20) return [{ left: 0, right: pageWidth }];
  const halfPageWidth = pageWidth * 0.55;
  const bodyItems = items.filter(it => it.width < halfPageWidth);
  if (bodyItems.length < 15) return [{ left: 0, right: pageWidth }];

  const pageTop = Math.min(...items.map(it => it.y));
  const pageBottom = Math.max(...items.map(it => it.y + it.height));
  const pageHeight = pageBottom - pageTop;
  if (pageHeight < 50) return [{ left: 0, right: pageWidth }];

  const numStrips = 8;
  const stripHeight = pageHeight / numStrips;
  const projWidth = Math.ceil(pageWidth);
  const searchLeft = Math.floor(projWidth * 0.30);
  const searchRight = Math.floor(projWidth * 0.70);

  interface StripValley { center: number; width: number; stripIdx: number; }
  const stripValleys: StripValley[] = [];

  for (let s = 0; s < numStrips; s++) {
    const stripTop = pageTop + s * stripHeight;
    const stripBottom = stripTop + stripHeight;
    const stripItems = bodyItems.filter(it => {
      const cy = it.y + it.height / 2;
      return cy >= stripTop && cy < stripBottom;
    });
    if (stripItems.length < 3) continue;

    const projection = new Array(projWidth).fill(0);
    for (const it of stripItems) {
      const left = Math.max(0, Math.floor(it.x));
      const right = Math.min(projWidth - 1, Math.floor(it.x + it.width));
      for (let px = left; px <= right; px++) projection[px]++;
    }

    let sum = 0;
    for (let i = searchLeft; i < searchRight; i++) sum += projection[i];
    const avg = sum / (searchRight - searchLeft);
    if (avg < 0.5) continue;
    const threshold = Math.max(0.5, avg * 0.1);

    let vs = -1;
    for (let i = searchLeft; i < searchRight; i++) {
      if (projection[i] <= threshold) { if (vs < 0) vs = i; }
      else { if (vs >= 0) { const w = i - vs; if (w >= 3) stripValleys.push({ center: (vs + i) / 2, width: w, stripIdx: s }); vs = -1; } }
    }
    if (vs >= 0) { const w = searchRight - vs; if (w >= 3) stripValleys.push({ center: (vs + searchRight) / 2, width: w, stripIdx: s }); }
  }

  if (stripValleys.length === 0) return [{ left: 0, right: pageWidth }];
  stripValleys.sort((a, b) => a.center - b.center);

  interface Cluster { centers: number[]; widths: number[]; strips: Set<number>; }
  const clusters: Cluster[] = [];
  for (const v of stripValleys) {
    let merged = false;
    for (const c of clusters) {
      const avgCenter = c.centers.reduce((a, b) => a + b, 0) / c.centers.length;
      if (Math.abs(v.center - avgCenter) <= 15) {
        c.centers.push(v.center); c.widths.push(v.width); c.strips.add(v.stripIdx);
        merged = true; break;
      }
    }
    if (!merged) clusters.push({ centers: [v.center], widths: [v.width], strips: new Set([v.stripIdx]) });
  }

  const validClusters = clusters.filter(c => c.strips.size >= 2).sort((a, b) => b.strips.size - a.strips.size);
  if (validClusters.length === 0) return [{ left: 0, right: pageWidth }];

  const best = validClusters[0];
  const gapCenter = best.centers.reduce((a, b) => a + b, 0) / best.centers.length;
  const gapWidth = Math.max(...best.widths);

  const votingStrips = best.strips;
  const votingItems = bodyItems.filter(it => {
    const cy = it.y + it.height / 2;
    const stripIdx = Math.floor((cy - pageTop) / stripHeight);
    return votingStrips.has(stripIdx);
  });
  const leftCount = votingItems.filter(it => it.x + it.width / 2 < gapCenter).length;
  const rightCount = votingItems.filter(it => it.x + it.width / 2 >= gapCenter).length;
  const totalVoting = votingItems.length;
  if (totalVoting < 10 || leftCount < totalVoting * 0.2 || rightCount < totalVoting * 0.2)
    return [{ left: 0, right: pageWidth }];

  let maxRightOfLeft = 0;
  let minLeftOfRight = pageWidth;
  const gapLeft = gapCenter - gapWidth / 2;
  const gapRight = gapCenter + gapWidth / 2;
  for (const it of bodyItems) {
    const center = it.x + it.width / 2;
    if (center < gapLeft) maxRightOfLeft = Math.max(maxRightOfLeft, it.x + it.width);
    else if (center > gapRight) minLeftOfRight = Math.min(minLeftOfRight, it.x);
  }
  if (minLeftOfRight - maxRightOfLeft < 3) { maxRightOfLeft = gapCenter - 2; minLeftOfRight = gapCenter + 2; }
  return [{ left: 0, right: maxRightOfLeft }, { left: minLeftOfRight, right: pageWidth }];
}

function detectFormula(text: string): boolean {
  const t = text.trim();
  if (!t || t.length > 600) return false;
  const mathUnicodeRe = /[\u0370-\u03FF\u2200-\u22FF\u2A00-\u2AFF\u27C0-\u27EF\u2190-\u21FF]/g;
  const mathUni = (t.match(mathUnicodeRe) || []).length;
  const mathAscii = (t.match(/[=+\-*/^_<>{}|·×÷≈≠≤≥∞]/g) || []).length;
  const proseWords = (t.match(/[A-Za-z\u4e00-\u9fa5]{3,}/g) || []).length;
  const sentencePunct = (t.match(/[.。!?！？]/g) || []).length;
  const totalLen = t.length;
  const mathRatio = (mathUni + mathAscii) / Math.max(1, totalLen);
  const hasSubSup = /[A-Za-z\u0370-\u03FF][_^]\s*[\w{(]/.test(t);
  const hasBackslashCmd = /\\[A-Za-z]+/.test(t);
  if (mathRatio > 0.18 && proseWords < 5) return true;
  if (hasSubSup && proseWords < 8) return true;
  if (hasBackslashCmd && proseWords < 8) return true;
  if (/^\(?\d+[a-z]?\)?$/.test(t)) return true;
  if (/^(algorithm|procedure)\s+\d/i.test(t)) return true;
  if (totalLen < 80 && sentencePunct === 0 && mathAscii > 3) return true;
  return false;
}

/** 判断段落是否为"不可交互"类型（表格、图、参考文献、算法） */
export function isNonInteractiveParagraph(para: Paragraph): boolean {
  const t = para.text.trim();
  if (/^(Figure|Fig\.?|图)\s*\d/i.test(t)) return true;
  if (/^(Table|表)\s*\d/i.test(t)) return true;
  if (/^(Algorithm|算法)\s*\d/i.test(t)) return true;
  if (/^\[\d+\]/.test(t)) return true;
  if (/^(References|参考文献|Bibliography)\s*$/i.test(t)) return true;
  if (para.isFormula) return true;
  if (t.length < 15 && para.fontSize < 8) return true;
  return false;
}
