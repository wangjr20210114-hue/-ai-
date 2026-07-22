import { describe, expect, it } from 'vitest';
import { hasTextSelectionInside } from './scrollSelection';
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
});
