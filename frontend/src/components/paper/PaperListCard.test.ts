import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import type { PaperInfo } from '../../types';
import { dedupePapers, paperArxivHref } from '../../services/paperUtils';

const paper = (id: string, title: string): PaperInfo => ({
  arxiv_id: id, title, authors: 'Author', year: 2026, abstract_zh: '',
  key_contribution: '', citations: 'arXiv', arxiv_url: '', pdf_url: '',
});

describe('dedupePapers', () => {
  it('removes repeated arXiv versions and repeated normalized titles', () => {
    const result = dedupePapers([
      paper('2601.00001v1', 'A Useful Paper'),
      paper('2601.00001v2', 'A Useful Paper'),
      paper('webpdf-1', 'A useful-paper'),
      paper('2601.00002', 'Another Paper'),
    ]);
    expect(result.map((item) => item.arxiv_id)).toEqual(['2601.00001v1', '2601.00002']);
  });

  it('derives the canonical arXiv page when the provider omits its URL', () => {
    expect(paperArxivHref(paper('2601.00001v2', 'A Useful Paper')))
      .toBe('https://arxiv.org/abs/2601.00001v2');
    expect(paperArxivHref(paper('webpdf-1', 'Public PDF'))).toBe('');
  });

  it('keeps exactly the reader and arXiv actions in the discovery card', () => {
    const source = readFileSync(
      new URL('./PaperListCard.tsx', import.meta.url),
      'utf8',
    );
    expect(source).toContain("t('startPaperAssistant')");
    expect(source).toContain("t('openArxiv')");
    expect(source).not.toContain("t('downloadPaper')");
    expect(source).not.toContain('savePdf');
    expect(source).not.toContain('<InfoCard');
  });
});
