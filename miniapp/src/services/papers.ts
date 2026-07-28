import type { PaperInfo } from '@floris/contracts'
import { apiRequest } from './request'

/**
 * The existing Makers paper resolver treats `webpaper-*` as a source-backed
 * result and resolves its public PDF URL instead of fabricating an arXiv URL.
 */
export function paperResolverId(paper: PaperInfo, now = Date.now()): string {
  return String(paper.arxiv_id || '').trim() || `webpaper-${now}`
}

export function savePaperToReading(paper: PaperInfo): Promise<unknown> {
  return apiRequest('/papers', {
    method: 'POST',
    data: {
      arxiv_id: paperResolverId(paper),
      title: paper.title,
      pdf_url: paper.pdf_url || '',
      source_url: paper.source_url || paper.arxiv_url || '',
    },
    timeout: 60_000,
  })
}
