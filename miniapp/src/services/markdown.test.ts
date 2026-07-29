import { describe, expect, it } from 'vitest'
import { decorateRichTextHtml, markdownToPlainText } from './markdown'

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

describe('decorateRichTextHtml', () => {
  it('injects inline styles into bare tags', () => {
    const html = decorateRichTextHtml('<h2>标题</h2><p>正文<strong>重点</strong></p>')
    expect(html).toContain('<h2 style=')
    expect(html).toContain('<p style=')
    expect(html).toContain('<strong style=')
  })

  it('rewrites pre/code blocks into a preserved-whitespace card', () => {
    const html = decorateRichTextHtml('<pre><code class="language-ts">const a = 1\nconst b = 2</code></pre>')
    expect(html).not.toContain('<pre')
    expect(html).toContain('white-space:pre-wrap')
    expect(html).toContain('const a = 1')
  })

  it('never double-injects tags that already carry a style', () => {
    const html = decorateRichTextHtml('<p style="color:red">已有样式</p>')
    expect(html.match(/style=/g)).toHaveLength(1)
    expect(html).toContain('color:red')
  })

  it('constrains tables with fixed layout and compact cells', () => {
    const html = decorateRichTextHtml('<table><thead><tr><th>角色</th></tr></thead><tbody><tr><td>模型拥有方</td></tr></tbody></table>')
    expect(html).toContain('table-layout:fixed')
    expect(html).toContain('font-size:20rpx')
    expect(html).toContain('word-break:break-word')
  })
})
