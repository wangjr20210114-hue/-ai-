import { extractParagraphs, loadPdf } from './pdf';
import { fetchPaperFile } from './paperApi';

export interface PdfInspection {
  isPaper: boolean;
  pageCount: number;
  title: string;
  preview: string;
}

/** Classify from PDF structure/text, not only the filename. */
export async function inspectPdf(file: File): Promise<PdfInspection> {
  const document = await loadPdf(await file.arrayBuffer());
  const pageTexts: string[] = [];
  for (let pageNumber = 1; pageNumber <= Math.min(3, document.numPages); pageNumber += 1) {
    const page = await document.getPage(pageNumber);
    const paragraphs = await extractParagraphs(page);
    pageTexts.push(paragraphs.map((paragraph) => paragraph.text).join('\n'));
  }
  const text = pageTexts.join('\n');
  const lower = text.toLowerCase();
  const signals = [
    /\babstract\b/.test(lower),
    /\bkeywords?\b/.test(lower),
    /\bdoi\b|arxiv[:.]/.test(lower),
    /\bintroduction\b/.test(lower),
    /\breferences\b|bibliography/.test(lower),
    /\b(university|institute|laboratory|department)\b/.test(lower),
  ].filter(Boolean).length;
  const firstLine = text.split('\n').map((line) => line.trim()).find((line) => line.length >= 8 && line.length <= 240);
  return {
    isPaper: signals >= 2,
    pageCount: document.numPages,
    title: firstLine || file.name.replace(/\.pdf$/i, ''),
    preview: text.replace(/\s+/g, ' ').slice(0, 1000),
  };
}

/** Extract a bounded text snapshot from a user-selected Makers Blob PDF. */
export async function extractStoredPdfText(fileId: string, maxChars = 60_000): Promise<string> {
  const response = await fetchPaperFile(fileId);
  if (!response.ok) throw new Error('无法读取这份文档，请确认文件仍在“我的阅读”中');
  const document = await loadPdf(await response.arrayBuffer());
  const pages: string[] = [];
  let length = 0;
  for (let pageNumber = 1; pageNumber <= document.numPages && length < maxChars; pageNumber += 1) {
    const page = await document.getPage(pageNumber);
    const text = (await extractParagraphs(page))
      .map((paragraph) => paragraph.text.trim())
      .filter(Boolean)
      .join('\n');
    if (!text) continue;
    pages.push(`[第 ${pageNumber} 页]\n${text}`);
    length += text.length;
  }
  const output = pages.join('\n\n').slice(0, maxChars).trim();
  if (!output) throw new Error('这份 PDF 没有可提取的文字，请在阅读器中查看或换一份文本型 PDF');
  return output;
}
