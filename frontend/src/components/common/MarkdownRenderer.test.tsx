import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import MarkdownRenderer from './MarkdownRenderer';

describe('MarkdownRenderer', () => {
  it('renders fenced code as a bounded language-labelled block', () => {
    const html = renderToStaticMarkup(
      <MarkdownRenderer content={'```python\nprint("' + 'x'.repeat(400) + '")\n```'} />,
    );
    expect(html).toContain('class="md-code-block"');
    expect(html).toContain('language-python');
    expect(html).toContain('aria-label="复制代码"');
    expect(html).toContain('hljs-built_in');
    expect(html).toContain('<pre');
  });

  it('wraps wide GFM tables in a horizontal scroll container', () => {
    const html = renderToStaticMarkup(
      <MarkdownRenderer content={'| 列一 | 列二 |\n| --- | --- |\n| 内容 | 内容 |'} />,
    );
    expect(html).toContain('class="md-table-wrap"');
    expect(html).toContain('<table>');
  });
});
