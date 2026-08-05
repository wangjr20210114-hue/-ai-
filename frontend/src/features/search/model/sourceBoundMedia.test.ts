import { describe, expect, it } from 'vitest';
import {
  remarkSourceBoundMedia,
  stripLegacyMediaMarkers,
  type MarkdownAstNode,
} from './sourceBoundMedia';
import type { RichMediaAsset, SearchResultItem } from './types';

const sources: SearchResultItem[] = [{
  id: 'source-1',
  source: 'wsa',
  title: 'AI 新闻',
  snippet: '新闻摘要',
  url: 'https://news.example/ai',
}];

const reviewed: RichMediaAsset = {
  id: 'media-1',
  kind: 'image',
  url: 'https://img.example/ai.jpg',
  source_id: 'source-1',
  source_url: 'https://news.example/ai',
  alt: 'AI 新闻图片',
  caption: 'AI 新闻图片',
  generated: false,
  vision_reviewed: true,
};

function paragraph(url: string): MarkdownAstNode {
  return {
    type: 'paragraph',
    children: [
      { type: 'text', value: '结论 ' },
      {
        type: 'link',
        url,
        children: [{ type: 'text', value: '来源' }],
      },
    ],
  };
}

function transform(
  media: RichMediaAsset[],
  sourceItems = sources,
  citationUrl = sources[0].url,
): MarkdownAstNode {
  const tree: MarkdownAstNode = {
    type: 'root',
    children: [paragraph(citationUrl), paragraph(citationUrl)],
  };
  const plugin = remarkSourceBoundMedia({ sources: sourceItems, media });
  plugin()(tree);
  return tree;
}

function insertedImages(tree: MarkdownAstNode): MarkdownAstNode[] {
  return (tree.children || []).filter((node) => node.type === 'image');
}

describe('remarkSourceBoundMedia', () => {
  it('inserts reviewed media once after the first exact source citation', () => {
    const tree = transform([reviewed]);
    const images = insertedImages(tree);

    expect(tree.children?.map((node) => node.type)).toEqual([
      'paragraph',
      'image',
      'paragraph',
    ]);
    expect(images).toHaveLength(1);
    expect(images[0].url).toBe(reviewed.url);
    expect(images[0].data?.hProperties).toEqual({
      'data-source-bound-media': 'media-1',
      'data-source-id': 'source-1',
    });
  });

  it.each([
    ['unreviewed', { ...reviewed, vision_reviewed: false }],
    ['wrong source id', { ...reviewed, source_id: 'source-missing' }],
    ['wrong source url', { ...reviewed, source_url: 'https://news.example/other' }],
  ])('fails closed for %s media', (_name, media) => {
    expect(insertedImages(transform([media]))).toHaveLength(0);
  });

  it('rejects source-bound candidates that did not pass visual review', () => {
    const fallback = {
      ...reviewed,
      vision_reviewed: false,
      vision_fallback: true,
      source_bound_fallback: true,
    };
    expect(insertedImages(transform([fallback]))).toHaveLength(0);
    expect(insertedImages(transform([{ ...fallback, source_url: 'https://news.example/other' }]))).toHaveLength(0);
  });

  it('does not accept redirect-like or normalized-near-match citation URLs', () => {
    expect(
      insertedImages(transform([reviewed], sources, 'https://redirect.example/?to=https://news.example/ai')),
    ).toHaveLength(0);
    expect(
      insertedImages(transform([reviewed], sources, 'https://news.example/ai/')),
    ).toHaveLength(0);
  });

  it('fails closed when a source id does not resolve uniquely', () => {
    const duplicateSources = [
      sources[0],
      { ...sources[0], url: 'https://news.example/other' },
    ];

    expect(insertedImages(transform([reviewed], duplicateSources))).toHaveLength(0);
  });

  it('never moves uncited reviewed images to the opening', () => {
    const tree: MarkdownAstNode = {
      type: 'root',
      children: [{
        type: 'paragraph',
        children: [{ type: 'text', value: 'Query-level verified summary' }],
      }],
    };
    remarkSourceBoundMedia({
      sources,
      media: [reviewed],
    })()(tree);

    expect(insertedImages(tree)).toHaveLength(0);
  });

  it('does not move uncited media while the answer can still add a citation', () => {
    const tree: MarkdownAstNode = {
      type: 'root',
      children: [{
        type: 'paragraph',
        children: [{ type: 'text', value: 'Streaming summary' }],
      }],
    };
    remarkSourceBoundMedia({ sources, media: [reviewed] })()(tree);
    expect(insertedImages(tree)).toHaveLength(0);
  });

  it('strips complete, indexed, and partial legacy markers without placing media', () => {
    expect(stripLegacyMediaMarkers(
      '第一段\n\n[[YUANBAO_MEDIA]]\n\n[[YUANBAO_MEDIA:2]]\n\n结尾[[YUANBAO_MED',
    )).toBe('第一段\n\n\n\n\n\n结尾');
    expect(stripLegacyMediaMarkers('正文[[YUANBAO_MEDIA: 1]]结束')).toBe('正文结束');
    expect(stripLegacyMediaMarkers('正文\n[[YUANBAO_MEDIA:')).toBe('正文\n');
  });
});
