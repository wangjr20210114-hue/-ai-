import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import MarkdownRenderer from './MarkdownRenderer';
import type { SearchMeta } from '../../types';

const searchMeta: SearchMeta = {
  query: 'AI 进展', results: [{
    id: 'source-1', source: 'wsa', title: 'AI 新闻', snippet: '新闻摘要',
    url: 'https://news.example/ai', image: 'https://img.example/card.jpg',
  }], images: ['https://img.example/one.jpg', 'https://img.example/two.jpg'],
  sources_used: [], total: 0,
  media: [
    { id: 'one', kind: 'image', url: 'https://img.example/one.jpg', alt: '第一张', caption: '第一张', generated: false },
    { id: 'two', kind: 'image', url: 'https://img.example/two.jpg', alt: '第二张', caption: '第二张', generated: false },
  ],
};

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

  it('keeps ordinary web evidence as a compact Markdown link instead of an InfoCard', () => {
    const html = renderToStaticMarkup(
      <MarkdownRenderer content={'参考 [AI 新闻](https://news.example/ai)。'} searchMeta={searchMeta} />,
    );
    expect(html).toContain('<a href="https://news.example/ai"');
    expect(html).toContain('>AI 新闻</a>');
    expect(html).not.toContain('新闻摘要');
    expect(html).not.toContain('card.jpg');
  });

  it('replaces model-selected media slots in paragraph order instead of appending a gallery', () => {
    const html = renderToStaticMarkup(
      <MarkdownRenderer
        content={'第一条进展。\n\n[[YUANBAO_MEDIA]]\n\n第二条进展。\n\n[[YUANBAO_MEDIA]]\n\n结论。'}
        searchMeta={searchMeta}
      />,
    );
    expect(html.indexOf('第一条进展')).toBeLessThan(html.indexOf('one.jpg'));
    expect(html.indexOf('one.jpg')).toBeLessThan(html.indexOf('第二条进展'));
    expect(html.indexOf('第二条进展')).toBeLessThan(html.indexOf('two.jpg'));
    expect(html).not.toContain('YUANBAO_MEDIA');
  });

  it('removes unused media slots when no reviewed image survived', () => {
    const html = renderToStaticMarkup(
      <MarkdownRenderer content={'正文\n\n[[YUANBAO_MEDIA]]\n\n结束'} searchMeta={{ ...searchMeta, media: [], images: [] }} />,
    );
    expect(html).toContain('正文');
    expect(html).toContain('结束');
    expect(html).not.toContain('YUANBAO_MEDIA');
    expect(html).not.toContain('<img');
  });

  it('uses AI-authored paragraph structure when async media arrives after an answer without slots', () => {
    const html = renderToStaticMarkup(
      <MarkdownRenderer
        content={'第一段解释 AI 进展。\n\n第二段补充影响。\n\n最后给出建议。'}
        searchMeta={{ ...searchMeta, media: [searchMeta.media[0]], images: [searchMeta.images[0]] }}
      />,
    );
    expect(html.indexOf('第一段解释')).toBeLessThan(html.indexOf('one.jpg'));
    expect(html.indexOf('one.jpg')).toBeLessThan(html.indexOf('第二段补充'));
    expect(html.indexOf('one.jpg')).not.toBeGreaterThan(html.indexOf('最后给出建议'));
  });

  it('does not move fallback media through an incomplete streaming answer', () => {
    const html = renderToStaticMarkup(
      <MarkdownRenderer
        streaming
        content={'第一段仍在流式生成。\n\n第二段尚未完成'}
        searchMeta={{ ...searchMeta, media: [searchMeta.media[0]], images: [searchMeta.images[0]] }}
      />,
    );
    expect(html).toContain('is-streaming');
    expect(html).not.toContain('one.jpg');
  });

  it('keeps an explicit model media slot visible during streaming', () => {
    const html = renderToStaticMarkup(
      <MarkdownRenderer
        streaming
        content={'已经完成的段落。\n\n[[YUANBAO_MEDIA]]\n\n继续生成'}
        searchMeta={{ ...searchMeta, media: [searchMeta.media[0]], images: [searchMeta.images[0]] }}
      />,
    );
    expect(html).toContain('one.jpg');
    expect(html).not.toContain('YUANBAO_MEDIA');
  });
});
