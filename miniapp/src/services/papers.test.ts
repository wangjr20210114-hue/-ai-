import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  apiRequest: vi.fn(),
}))

vi.mock('./request', () => ({
  apiRequest: mocks.apiRequest,
}))

import { paperResolverId, savePaperToReading } from './papers'

describe('paper result bridge', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.apiRequest.mockResolvedValue({ file_id: 'saved-paper' })
  })

  it('preserves a verified arXiv id', () => {
    expect(paperResolverId({ title: 'Attention', arxiv_id: '1706.03762' }, 1))
      .toBe('1706.03762')
  })

  it('uses the existing source-backed resolver contract when no arXiv id exists', () => {
    expect(paperResolverId({ title: 'A public paper', source_url: 'https://example.com/paper' }, 42))
      .toBe('webpaper-42')
  })

  it('delegates PDF resolution and persistence to the Makers paper endpoint', async () => {
    await savePaperToReading({
      title: 'A public paper',
      pdf_url: 'https://example.com/paper.pdf',
      source_url: 'https://example.com/paper',
    })
    expect(mocks.apiRequest).toHaveBeenCalledWith('/papers', expect.objectContaining({
      method: 'POST',
      data: expect.objectContaining({
        arxiv_id: expect.stringMatching(/^webpaper-/),
        title: 'A public paper',
        pdf_url: 'https://example.com/paper.pdf',
      }),
    }))
  })
})
