import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import MarkdownRenderer from './MarkdownRenderer';
import { loadMarkdownEnhancements } from './markdownEnhancements';
import type { SearchMeta } from '../../features/search/model';
import { LanguageProvider } from '../../i18n';

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
  it('renders fenced code as a bounded language-labelled block', async () => {
    // Highlighting loads asynchronously after first paint in the app.
    await loadMarkdownEnhancements();
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

  it('keeps ordinary web evidence as a compact Markdown link', () => {
    const html = renderToStaticMarkup(
      <MarkdownRenderer content={'参考 [AI 新闻](https://news.example/ai)。'} searchMeta={searchMeta} />,
    );
    expect(html).toContain('<a href="https://news.example/ai"');
    expect(html).toContain('>AI 新闻</a>');
    expect(html).not.toContain('新闻摘要');
    expect(html).not.toContain('card.jpg');
  });

  it('does not present retrieved-but-unused results as answer citations', () => {
    const html = renderToStaticMarkup(
      <MarkdownRenderer content={'这里是综合后的结论。'} searchMeta={searchMeta} />,
    );
    expect(html).not.toContain('class="search-evidence-links"');
    expect(html).not.toContain('href="https://news.example/ai"');
  });

  it('does not flash the full source directory before inline citations stream in', () => {
    const html = renderToStaticMarkup(
      <MarkdownRenderer streaming content={'正在组织第一条进展。'} searchMeta={searchMeta} />,
    );
    expect(html).not.toContain('class="search-evidence-links"');
    expect(html).not.toContain('href="https://news.example/ai"');
  });

  it('turns a URL-only Markdown link into a small clickable inline citation', () => {
    const html = renderToStaticMarkup(
      <MarkdownRenderer content={'结论（[https://news.example/ai](https://news.example/ai)）。'} searchMeta={searchMeta} />,
    );
    expect(html).toContain('href="https://news.example/ai"');
    expect(html).toContain('class="md-citation-link"');
    expect(html).toContain('>查看来源 · news.example</a>');
    expect(html).not.toContain('>https://news.example/ai</a>');
  });

  it('turns an explicit source label into the same small inline citation', () => {
    const html = renderToStaticMarkup(
      <MarkdownRenderer content={'结论[来源](https://news.example/ai)。'} searchMeta={searchMeta} />,
    );
    expect(html).toContain('href="https://news.example/ai"');
    expect(html).toContain('class="md-citation-link"');
    expect(html).toContain('title="https://news.example/ai"');
    expect(html).toContain('>查看来源 · news.example</a>');
  });

  it('renders a source label in the active English interface language', () => {
    const originalStorage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      value: {
        getItem: () => 'en',
        setItem: () => undefined,
        removeItem: () => undefined,
        clear: () => undefined,
        key: () => null,
        length: 0,
      } satisfies Storage,
    });
    try {
      const html = renderToStaticMarkup(
        <LanguageProvider>
          <MarkdownRenderer content={'Conclusion [来源](https://news.example/ai).'} searchMeta={searchMeta} />
        </LanguageProvider>,
      );
      expect(html).toContain('>View source · news.example</a>');
      expect(html).not.toContain('>来源</a>');
    } finally {
      if (originalStorage) Object.defineProperty(globalThis, 'localStorage', originalStorage);
      else delete (globalThis as { localStorage?: Storage }).localStorage;
    }
  });

  it('repairs a bare parenthesized provider URL into a titled clickable source', () => {
    const html = renderToStaticMarkup(
      <MarkdownRenderer content={'事实说明。(https://news.example/ai)'} searchMeta={searchMeta} />,
    );
    expect(html).toContain('href="https://news.example/ai"');
    expect(html).toContain('>查看来源 · news.example</a>');
    expect(html).toContain('target="_blank"');
  });

  it('strips legacy media markers and never uses them to place images', () => {
    const html = renderToStaticMarkup(
      <MarkdownRenderer
        content={'第一条进展。\n\n[[YUANBAO_MEDIA]]\n\n第二条进展。\n\n[[YUANBAO_MEDIA]]\n\n结论。'}
        searchMeta={searchMeta}
      />,
    );
    expect(html).not.toContain('one.jpg');
    expect(html).not.toContain('two.jpg');
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

  it('does not guess a media position when the model omitted Markdown images', () => {
    const html = renderToStaticMarkup(
      <MarkdownRenderer
        content={'第一段解释 AI 进展。\n\n第二段补充影响。\n\n最后给出建议。'}
        searchMeta={{ ...searchMeta, media: [searchMeta.media[0]], images: [searchMeta.images[0]] }}
      />,
    );
    expect(html).not.toContain('one.jpg');
  });

  it('places reviewed media only after the paragraph citing its exact source', () => {
    const sourceBound = {
      ...searchMeta.media[0],
      source_id: 'source-1',
      source_url: 'https://news.example/ai',
      vision_reviewed: true,
    };
    const html = renderToStaticMarkup(
      <MarkdownRenderer
        content={'第一段解释。[AI 新闻](https://news.example/ai)\n\n第二段补充影响。'}
        searchMeta={{ ...searchMeta, media: [sourceBound], images: [sourceBound.url] }}
      />,
    );
    expect(html.indexOf('第一段解释')).toBeLessThan(html.indexOf('one.jpg'));
    expect(html.indexOf('one.jpg')).toBeLessThan(html.indexOf('第二段补充影响'));
    expect((html.match(/one\.jpg/g) || [])).toHaveLength(1);
    expect(html).toContain('data-source-id="source-1"');
    expect(html).toContain('data-source-bound-media="one"');
  });

  it('fails closed when media source identity does not match the cited source', () => {
    const mismatched = {
      ...searchMeta.media[0],
      source_id: 'source-1',
      source_url: 'https://other.example/wrong',
      vision_reviewed: true,
    };
    const html = renderToStaticMarkup(
      <MarkdownRenderer
        content={'第一段解释。[AI 新闻](https://news.example/ai)\n\n第二段。'}
        searchMeta={{ ...searchMeta, media: [mismatched], images: [mismatched.url] }}
      />,
    );
    expect(html).not.toContain('one.jpg');
  });

  it('does not insert an unreviewed fallback even when its source is cited', () => {
    const unreviewed = {
      ...searchMeta.media[0],
      source_id: 'source-1',
      source_url: 'https://news.example/ai',
      vision_reviewed: false,
    };
    const html = renderToStaticMarkup(
      <MarkdownRenderer
        content={'第一段解释。[AI 新闻](https://news.example/ai)\n\n第二段。'}
        searchMeta={{ ...searchMeta, media: [unreviewed], images: [unreviewed.url] }}
      />,
    );
    expect(html).not.toContain('one.jpg');
  });

  it('renders an explicit SearchPro fallback only through exact source binding', () => {
    const fallback = {
      ...searchMeta.media[0],
      source_id: 'source-1',
      source_url: 'https://news.example/ai',
      vision_reviewed: false,
      vision_fallback: true,
      source_bound_fallback: true,
    };
    const html = renderToStaticMarkup(
      <MarkdownRenderer
        streaming
        content={'第一条进展。[来源](https://news.example/ai)'}
        searchMeta={{ ...searchMeta, media: [fallback], images: [fallback.url] }}
      />,
    );
    expect(html).toContain('one.jpg');
    expect(html).toContain('data-source-id="source-1"');
  });

  it('rejects a model-authored searched image even when its URL was reviewed', () => {
    const sourceBound = {
      ...searchMeta.media[0],
      source_id: 'source-1',
      source_url: 'https://news.example/ai',
      vision_reviewed: true,
    };
    const html = renderToStaticMarkup(
      <MarkdownRenderer
        streaming
        content={'第一段仍在流式生成。\n\n![第一张](https://img.example/one.jpg)\n\n第二段尚未完成'}
        searchMeta={{ ...searchMeta, media: [sourceBound], images: [sourceBound.url] }}
      />,
    );
    expect(html).toContain('is-streaming');
    expect(html).not.toContain('one.jpg');
  });

  it('renders Markdown formatting while the answer is still streaming', () => {
    const html = renderToStaticMarkup(
      <MarkdownRenderer streaming content={'### 实时标题\n\n这是 **重点内容**。'} />,
    );
    expect(html).toContain('<h3>实时标题</h3>');
    expect(html).toContain('<strong>重点内容</strong>');
    expect(html).not.toContain('### 实时标题');
    expect(html).not.toContain('**重点内容**');
  });

  it('hides historical media that has only a legacy slot', () => {
    const html = renderToStaticMarkup(
      <MarkdownRenderer
        streaming
        content={'已经完成的段落。\n\n[[YUANBAO_MEDIA]]\n\n继续生成'}
        searchMeta={{ ...searchMeta, media: [searchMeta.media[0]], images: [searchMeta.images[0]] }}
      />,
    );
    expect(html).not.toContain('one.jpg');
    expect(html).not.toContain('YUANBAO_MEDIA');
  });

  it('does not expose a provider preview before vision review completes', () => {
    const preview = { ...searchMeta.media[0], id: 'preview-one', preview: true };
    const html = renderToStaticMarkup(
      <MarkdownRenderer
        streaming
        content={'第一段已经生成。\n\n[[YUANBAO_MEDIA]]\n\n继续生成'}
        searchMeta={{ ...searchMeta, media: [], images: [], preview_media: [preview], media_pending: true }}
      />,
    );
    expect(html).not.toContain('one.jpg');
    expect(html).not.toContain('YUANBAO_MEDIA');
  });

  it('does not retain a rejected preview after media review finishes', () => {
    const preview = { ...searchMeta.media[0], id: 'preview-one', preview: true };
    const html = renderToStaticMarkup(
      <MarkdownRenderer
        content={'正文。\n\n[[YUANBAO_MEDIA]]'}
        searchMeta={{ ...searchMeta, media: [], images: [], preview_media: [preview], media_pending: false }}
      />,
    );
    expect(html).not.toContain('one.jpg');
    expect(html).not.toContain('图片核实中');
  });

  it('exposes safe media diagnostics without rendering technical copy', () => {
    const html = renderToStaticMarkup(
      <MarkdownRenderer
        content="Verified answer"
        searchMeta={{
          ...searchMeta,
          media: [],
          images: [],
          vision_diagnostics: {
            candidates: 4,
            reviewed: 2,
            approved: 0,
            source_bound_fallback: 0,
          },
        }}
      />,
    );
    expect(html).toContain('data-search-media-count="0"');
    expect(html).toContain('data-search-vision-candidates="4"');
    expect(html).toContain('data-search-vision-reviewed="2"');
    expect(html).not.toContain('vision_diagnostics');
  });

  it('shows completed query-relevant media even when its source was not cited inline', () => {
    const sourceBound = {
      ...searchMeta.media[0],
      source_id: 'source-1',
      source_url: 'https://news.example/ai',
      vision_reviewed: true,
    };
    const completed = renderToStaticMarkup(
      <MarkdownRenderer
        content="Completed verified summary without an inline link."
        searchMeta={{ ...searchMeta, media: [sourceBound] }}
      />,
    );
    const streaming = renderToStaticMarkup(
      <MarkdownRenderer
        streaming
        content="Still streaming and may add an inline link."
        searchMeta={{ ...searchMeta, media: [sourceBound] }}
      />,
    );
    expect(completed).toContain('data-source-bound-media="one"');
    expect(completed).toContain('href="https://news.example/ai"');
    expect(streaming).not.toContain('data-source-bound-media="one"');
  });

  it('does not repeat source-bound reviewed images with the same caption', () => {
    const sourceBound = {
      ...searchMeta.media[0],
      source_id: 'source-1',
      source_url: 'https://news.example/ai',
      vision_reviewed: true,
    };
    const duplicate = {
      ...sourceBound,
      id: 'duplicate',
      url: 'https://img.example/duplicate.jpg',
    };
    const html = renderToStaticMarkup(
      <MarkdownRenderer
        content={'第一段。[来源](https://news.example/ai)\n\n第二段。'}
        searchMeta={{ ...searchMeta, media: [sourceBound, duplicate] }}
      />,
    );
    expect(html).toContain('one.jpg');
    expect(html).not.toContain('duplicate.jpg');
  });
});
