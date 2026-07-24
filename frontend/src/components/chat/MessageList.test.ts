import { describe, expect, it } from 'vitest';
import { autoFollowAfterScroll, hasTextSelectionInside } from './scrollSelection';
import { streamingMarkdownAnswer } from './streamingAnswer';

describe('message selection auto-follow guard', () => {
  it('recognizes a non-collapsed selection inside the chat container', () => {
    const selectedNode = {} as Node;
    const container = { contains: (node: Node) => node === selectedNode } as HTMLElement;
    const selection = { isCollapsed: false, anchorNode: selectedNode } as unknown as Selection;
    expect(hasTextSelectionInside(container, selection)).toBe(true);
  });

  it('does not pause for a collapsed caret or an outside selection', () => {
    const selectedNode = {} as Node;
    const container = { contains: () => false } as unknown as HTMLElement;
    expect(hasTextSelectionInside(container, { isCollapsed: true, anchorNode: selectedNode } as unknown as Selection)).toBe(false);
    expect(hasTextSelectionInside(container, { isCollapsed: false, anchorNode: selectedNode } as unknown as Selection)).toBe(false);
  });

  it('detaches immediately when the user scrolls upward near the bottom', () => {
    expect(autoFollowAfterScroll(true, 1000, 996, 4)).toBe(false);
    expect(autoFollowAfterScroll(false, 996, 998, 2)).toBe(true);
  });

  it('stays detached until the user really reaches the bottom', () => {
    expect(autoFollowAfterScroll(false, 800, 850, 24)).toBe(false);
    expect(autoFollowAfterScroll(false, 850, 874, 0)).toBe(true);
  });
});

describe('streaming Markdown answer', () => {
  it('keeps renderable Markdown and complete media slots while hiding partial markers', () => {
    expect(streamingMarkdownAnswer('**重点**\n\n[[YUANBAO_MEDIA: 1]]\n\n继续'))
      .toBe('**重点**\n\n[[YUANBAO_MEDIA: 1]]\n\n继续');
    expect(streamingMarkdownAnswer('正文\n[[YUANBAO_MED')).toBe('正文\n');
  });

  it('hides an incomplete Markdown image tail and restores it when complete', () => {
    expect(streamingMarkdownAnswer('正文\n\n![新闻图片](https://img.example/part')).toBe('正文\n\n');
    expect(streamingMarkdownAnswer('正文\n\n![新闻图片](https://img.example/full.jpg)'))
      .toBe('正文\n\n![新闻图片](https://img.example/full.jpg)');
  });

  it('does not expose an unfinished emphasis delimiter', () => {
    expect(streamingMarkdownAnswer('正文\n\n**正在生成的重点')).toBe('正文\n\n');
    expect(streamingMarkdownAnswer('正文\n\n**完整重点**')).toBe('正文\n\n**完整重点**');
    expect(streamingMarkdownAnswer('正文\n\n~~尚未结束')).toBe('正文\n\n');
  });
});
