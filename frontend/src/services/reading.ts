import { extractParagraphs, loadPdf } from './pdf';

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
