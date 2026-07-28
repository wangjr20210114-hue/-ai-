import { describe, expect, it } from 'vitest'
import { markdownToPlainText } from './markdown'

describe('markdownToPlainText', () => {
  it('keeps answer text while removing rich media and URL targets', () => {
    const value = markdownToPlainText([
      '## 结论',
      '**新进展**见[报道](https://example.com/news)。',
      '![配图](https://example.com/a.jpg)',
      'https://example.com/source',
    ].join('\n'))
    expect(value).toContain('结论')
    expect(value).toContain('新进展见报道')
    expect(value).not.toContain('https://')
    expect(value).not.toContain('配图')
  })
})
